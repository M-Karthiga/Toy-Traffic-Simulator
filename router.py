"""Routing for the traffic simulator."""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple


class Router:
    """Shortest-path router over the road network."""

    def __init__(self) -> None:
        self._adjacency: Dict[str, List[Tuple[str, str, float]]] = {}
        self._route_cache: Dict[Tuple[str, str], Optional[Tuple[List[str], List[str]]]] = {}

    def add_node(self, node_id: str) -> None:
        self._adjacency.setdefault(node_id, [])

    def add_edge(self, from_node: str, to_node: str, road_id: str, cost: float) -> None:
        self.add_node(from_node)
        self.add_node(to_node)
        self._adjacency[from_node].append((to_node, road_id, cost))

    def build_from_network(self, roads: Dict[str, object], node_ids: List[str]) -> None:
        self._adjacency = {node_id: [] for node_id in node_ids}
        self._route_cache.clear()
        for road in roads.values():
            self.add_edge(
                road.from_node,
                road.to_node,
                road.road_id,
                road.length / max(1.0, road.speed_limit),
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
