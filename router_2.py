"""Multi-path router with proportional flow splitting.

Algorithm
---------
* Yen's K-shortest loopless paths (K = up to 4) for each (source, sink) pair.
* Each path is assigned a selection weight  w_i = 1 / cost_i  so that
  shorter / cheaper paths attract proportionally more vehicles while longer
  alternative paths still receive a non-zero share.
* Every vehicle independently draws a path from the weighted distribution,
  which naturally spreads traffic across the network over time.

Indian left-keep lane helpers are preserved unchanged.
"""

from __future__ import annotations

import heapq
import math
import random
from typing import Dict, List, Optional, Tuple


# Number of alternative paths to discover per (source, sink) pair.
_K_PATHS = 4


class Router:
    """Multi-path router over the road network."""

    def __init__(self) -> None:
        self._adjacency: Dict[str, List[Tuple[str, str, float]]] = {}
        # Cache: (src, dst) -> list of (node_path, road_path, cost)
        self._paths_cache: Dict[Tuple[str, str], List[Tuple[List[str], List[str], float]]] = {}
        # node_id -> (x, y) for geometry-based turn classification
        self._positions: Dict[str, Tuple[float, float]] = {}
        # RNG for stochastic path selection
        self._rng = random.Random(0)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, pos: Tuple[float, float] = (0.0, 0.0)) -> None:
        self._adjacency.setdefault(node_id, [])
        self._positions[node_id] = pos

    def add_edge(self, from_node: str, to_node: str, road_id: str, cost: float) -> None:
        self.add_node(from_node)
        self.add_node(to_node)
        self._adjacency[from_node].append((to_node, road_id, cost))

    def build_from_network(
        self,
        roads: Dict[str, object],
        node_ids: List[str],
        node_positions: Optional[Dict[str, Tuple[float, float]]] = None,
    ) -> None:
        self._adjacency = {node_id: [] for node_id in node_ids}
        self._paths_cache.clear()
        if node_positions:
            self._positions.update(node_positions)
        for road in roads.values():
            base_cost = road.length / max(1.0, road.speed_limit)
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

    # ------------------------------------------------------------------
    # Internal: single-path Dijkstra with optional edge/node blocking
    # ------------------------------------------------------------------

    def _dijkstra(
        self,
        source_id: str,
        sink_id: str,
        blocked_edges: Optional[set] = None,
        blocked_nodes: Optional[set] = None,
    ) -> Optional[Tuple[List[str], List[str], float]]:
        """Return (node_path, road_path, total_cost) or None."""
        if source_id not in self._adjacency or sink_id not in self._adjacency:
            return None

        dist: Dict[str, float] = {source_id: 0.0}
        prev: Dict[str, Optional[str]] = {source_id: None}
        pq: List[Tuple[float, str]] = [(0.0, source_id)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, float("inf")):
                continue
            if u == sink_id:
                break
            if blocked_nodes and u != source_id and u in blocked_nodes:
                continue
            for v, road_id, cost in self._adjacency.get(u, []):
                if blocked_edges and (u, v) in blocked_edges:
                    continue
                if blocked_nodes and v in blocked_nodes and v != sink_id:
                    continue
                nd = d + cost
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        if sink_id not in dist:
            return None

        node_path: List[str] = []
        cur: Optional[str] = sink_id
        while cur is not None:
            node_path.append(cur)
            cur = prev.get(cur)
        node_path.reverse()

        road_path: List[str] = []
        for i in range(len(node_path) - 1):
            rid = self.road_for_edge(node_path[i], node_path[i + 1])
            if rid is None:
                return None
            road_path.append(rid)

        return node_path, road_path, dist[sink_id]

    # ------------------------------------------------------------------
    # Yen's K-shortest loopless paths
    # ------------------------------------------------------------------

    def _path_cost(self, node_path: List[str]) -> Optional[float]:
        total = 0.0
        for i in range(len(node_path) - 1):
            found = False
            for v, _, cost in self._adjacency.get(node_path[i], []):
                if v == node_path[i + 1]:
                    total += cost
                    found = True
                    break
            if not found:
                return None
        return total

    def _yen_k_shortest(
        self, source_id: str, sink_id: str, K: int = _K_PATHS
    ) -> List[Tuple[List[str], List[str], float]]:
        """Return up to K shortest loopless paths sorted by ascending cost."""
        first = self._dijkstra(source_id, sink_id)
        if first is None:
            return []

        results: List[Tuple[List[str], List[str], float]] = [first]
        # Min-heap of candidate paths: (cost, node_path, road_path)
        candidates: List[Tuple[float, List[str], List[str]]] = []
        seen_node_paths = {tuple(first[0])}

        for k in range(1, K):
            prev_nodes, prev_roads, _ = results[k - 1]

            for spur_idx in range(len(prev_nodes) - 1):
                spur_node = prev_nodes[spur_idx]
                root_nodes = prev_nodes[: spur_idx + 1]
                root_roads = prev_roads[:spur_idx]

                # Block edges used by already-found paths sharing the same root
                blocked_edges: set = set()
                for path_nodes, path_roads, _ in results:
                    if (path_nodes[: spur_idx + 1] == root_nodes
                            and spur_idx < len(path_roads)):
                        blocked_edges.add(
                            (path_nodes[spur_idx], path_nodes[spur_idx + 1])
                        )

                # Block intermediate root nodes to prevent loops
                blocked_nodes: set = set(root_nodes[:-1])

                spur = self._dijkstra(
                    spur_node, sink_id, blocked_edges, blocked_nodes
                )
                if spur is None:
                    continue
                spur_nodes, spur_roads, _ = spur

                full_nodes = root_nodes[:-1] + spur_nodes
                full_roads = root_roads + spur_roads

                total_cost = self._path_cost(full_nodes)
                if total_cost is None:
                    continue

                path_key = tuple(full_nodes)
                if path_key in seen_node_paths:
                    continue
                seen_node_paths.add(path_key)
                heapq.heappush(candidates, (total_cost, full_nodes, full_roads))

            if not candidates:
                break

            best_cost, best_nodes, best_roads = heapq.heappop(candidates)
            results.append((best_nodes, best_roads, best_cost))

        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _ensure_paths_cached(self, source_id: str, sink_id: str) -> None:
        key = (source_id, sink_id)
        if key not in self._paths_cache:
            self._paths_cache[key] = self._yen_k_shortest(
                source_id, sink_id, K=_K_PATHS
            )

    def plan_route(
        self, source_id: str, sink_id: str
    ) -> Optional[Tuple[List[str], List[str]]]:
        """Return a (node_path, road_path) sampled proportionally to 1/path_cost.

        Shorter paths are selected more often; longer alternatives still
        receive traffic, naturally distributing load across the network.

        Selection probability:
            P(path_i) = (1/cost_i) / sum_j(1/cost_j)

        So if costs are [10, 20, 40], weights are [4/7, 2/7, 1/7] — the
        shortest path gets 4x the traffic of the longest, but the longest
        still carries 1/7 of vehicles rather than zero.
        """
        self._ensure_paths_cached(source_id, sink_id)
        paths = self._paths_cache.get((source_id, sink_id), [])
        if not paths:
            return None
        if len(paths) == 1:
            nodes, roads, _ = paths[0]
            return nodes, roads

        # Weight each path by 1/cost — lower cost = higher share
        weights = [1.0 / max(p[2], 1e-9) for p in paths]
        chosen_nodes, chosen_roads, _ = self._rng.choices(paths, weights=weights, k=1)[0]
        return chosen_nodes, chosen_roads

    def path_distribution(
        self, source_id: str, sink_id: str
    ) -> List[Tuple[List[str], float]]:
        """Return [(node_path, probability), ...] for diagnostics / logging."""
        self._ensure_paths_cached(source_id, sink_id)
        paths = self._paths_cache.get((source_id, sink_id), [])
        if not paths:
            return []
        weights = [1.0 / max(p[2], 1e-9) for p in paths]
        total = sum(weights)
        return [(p[0], w / total) for p, w in zip(paths, weights)]

    # ------------------------------------------------------------------
    # Indian left-keep lane classification helpers  (unchanged)
    # ------------------------------------------------------------------

    def classify_turn(self, prev_node: str, junction_node: str, next_node: str) -> str:
        """Return 'left', 'straight', or 'right' using bearing change.

        Bearing of incoming road = direction FROM prev_node TO junction_node.
        Bearing of outgoing road = direction FROM junction_node TO next_node.
        Signed angle (cross product sign) determines turn direction.
        India drives LEFT, so:
          negative cross (right-hand turn in standard coords with y-down) -> LEFT turn
          positive cross -> RIGHT turn
        """
        p = self._positions.get(prev_node, (0.0, 0.0))
        j = self._positions.get(junction_node, (0.0, 0.0))
        n = self._positions.get(next_node, (0.0, 0.0))

        in_dx = j[0] - p[0]
        in_dy = j[1] - p[1]
        out_dx = n[0] - j[0]
        out_dy = n[1] - j[1]

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
        Left turn  -> lane 0 (leftmost)
        Straight   -> middle lanes (1 to n-2), falling back to any
        Right turn -> lane n-1 (rightmost)
        Single-lane road: always [0].
        """
        if lane_count == 1:
            return [0]
        if turn == "left":
            return [0]
        if turn == "right":
            return [lane_count - 1]
        middle = list(range(1, lane_count - 1)) or [0]
        return middle

    def get_turn_for_vehicle(self, route_nodes: List[str], route_cursor: int) -> str:
        """Return turn classification for a vehicle currently on route_roads[route_cursor].

        route_cursor is the index into route_roads of the road the vehicle is ON.
        The junction is route_nodes[route_cursor + 1].
        The next road leads to route_nodes[route_cursor + 2].
        """
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