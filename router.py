
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Tuple


class Router:
    """Shortest-path router over the road network."""

    def __init__(self) -> None:
        self._adjacency: Dict[str, List[Tuple[str, str, float]]] = {}
        self._route_cache: Dict[Tuple[str, str], Optional[Tuple[List[str], List[str]]]] = {}
        # node_id → (x, y) for geometry-based turn classification
        self._positions: Dict[str, Tuple[float, float]] = {}

    def add_node(self, node_id: str, pos: Tuple[float, float] = (0.0, 0.0)) -> None:
        self._adjacency.setdefault(node_id, [])
        self._positions[node_id] = pos

    def add_edge(self, from_node: str, to_node: str, road_id: str, cost: float) -> None:
        self.add_node(from_node)
        self.add_node(to_node)
        self._adjacency[from_node].append((to_node, road_id, cost))

    def build_from_network(self, roads: Dict[str, object], node_ids: List[str],
                           node_positions: Optional[Dict[str, Tuple[float, float]]] = None) -> None:
        self._adjacency = {node_id: [] for node_id in node_ids}
        self._route_cache.clear()
        if node_positions:
            self._positions.update(node_positions)
        for road in roads.values():
            # Fewer lanes = higher cost (single-lane street costs more than 4-lane road)
            # Base cost = travel time at free-flow speed
            base_cost = road.length / max(1.0, road.speed_limit)
            # Lane penalty: inversely scale by lanes (1 lane → ×2.0, 4 lanes → ×0.5)
            lane_factor = 2.0 / max(1, road.lanes)
            self.add_edge(
                road.from_node,
                road.to_node,
                road.road_id,
                base_cost * lane_factor,
            )

    def road_for_edge(self, from_node: str, to_node: str) -> Optional[str]:
        for neighbour, road_id, _ in self._adjacency.get(from_node, []):
            if neighbour == to_node:
                return road_id
        return None

    def plan_route(self, source_id: str, sink_id: str) -> Optional[Tuple[List[str], List[str]]]:
        cache_key = (source_id, sink_id)
        if cache_key in self._route_cache:
            return self._route_cache[cache_key]

        if source_id not in self._adjacency or sink_id not in self._adjacency:
            self._route_cache[cache_key] = None
            return None

        distances: Dict[str, float] = {source_id: 0.0}
        previous: Dict[str, Optional[str]] = {source_id: None}
        pq: List[Tuple[float, str]] = [(0.0, source_id)]

        while pq:
            current_distance, node_id = heapq.heappop(pq)
            if current_distance > distances.get(node_id, float("inf")):
                continue
            if node_id == sink_id:
                break
            for neighbour, _, cost in self._adjacency.get(node_id, []):
                new_distance = current_distance + cost
                if new_distance < distances.get(neighbour, float("inf")):
                    distances[neighbour] = new_distance
                    previous[neighbour] = node_id
                    heapq.heappush(pq, (new_distance, neighbour))

        if sink_id not in distances:
            self._route_cache[cache_key] = None
            return None

        node_path: List[str] = []
        cursor: Optional[str] = sink_id
        while cursor is not None:
            node_path.append(cursor)
            cursor = previous.get(cursor)
        node_path.reverse()

        road_path: List[str] = []
        for index in range(len(node_path) - 1):
            road_id = self.road_for_edge(node_path[index], node_path[index + 1])
            if road_id is None:
                self._route_cache[cache_key] = None
                return None
            road_path.append(road_id)

        result = (node_path, road_path)
        self._route_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Indian left-keep lane classification helpers
    # ------------------------------------------------------------------

    def classify_turn(self, prev_node: str, junction_node: str, next_node: str) -> str:
        """Return 'left', 'straight', or 'right' using bearing change.

        Bearing of incoming road = direction FROM prev_node TO junction_node.
        Bearing of outgoing road = direction FROM junction_node TO next_node.
        Signed angle (cross product sign) determines turn direction.
        India drives LEFT, so:
          negative cross (right-hand turn in standard coords with y-down) → LEFT turn
          positive cross → RIGHT turn
        """
        p = self._positions.get(prev_node, (0.0, 0.0))
        j = self._positions.get(junction_node, (0.0, 0.0))
        n = self._positions.get(next_node, (0.0, 0.0))

        in_dx = j[0] - p[0]
        in_dy = j[1] - p[1]
        out_dx = n[0] - j[0]
        out_dy = n[1] - j[1]

        # Signed angle via cross product (screen coords: y increases downward)
        cross = in_dx * out_dy - in_dy * out_dx
        dot = in_dx * out_dx + in_dy * out_dy
        angle = math.degrees(math.atan2(cross, dot))

        if angle < -45:
            return "left"
        if angle > 45:
            return "right"
        return "straight"

    def preferred_lanes_india(self, turn: str, lane_count: int) -> List[int]:
        """Return ordered list of preferred lane indices for an Indian left-keep rule.

        Lane 0 = leftmost (slow/kerb side), lane n-1 = rightmost (fast/centre).
        • Left turn  → lane 0 (leftmost)
        • Straight   → middle lanes (1 … n-2), falling back to any
        • Right turn → lane n-1 (rightmost)
        Single-lane road: always [0].
        """
        if lane_count == 1:
            return [0]
        if turn == "left":
            return [0]
        if turn == "right":
            return [lane_count - 1]
        # straight: prefer middle lanes
        middle = list(range(1, lane_count - 1)) or [0]
        return middle

    def get_turn_for_vehicle(self, route_nodes: List[str], route_cursor: int) -> str:
        """Return turn classification for a vehicle currently on route_roads[route_cursor].

        route_cursor is the index into route_roads of the road the vehicle is ON.
        The junction is route_nodes[route_cursor + 1].
        The next road leads to route_nodes[route_cursor + 2].
        """
        # Need three nodes: prev, junction, next
        prev_idx = route_cursor
        junc_idx = route_cursor + 1
        next_idx = route_cursor + 2
        if prev_idx < 0 or next_idx >= len(route_nodes):
            return "straight"
        return self.classify_turn(
            route_nodes[prev_idx],
            route_nodes[junc_idx],
            route_nodes[next_idx],
        )