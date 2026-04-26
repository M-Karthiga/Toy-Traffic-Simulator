"""Vehicle model used by the lane-based traffic simulator."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import ClassVar, List, Optional


_vehicle_ids = itertools.count(1)


@dataclass
class Vehicle:
    """A routed vehicle that occupies exactly one road cell at a time."""

    source_id: str
    destination_id: str
    route_nodes: List[str]
    route_roads: List[str]
    vehicle_id: int = field(default_factory=lambda: next(_vehicle_ids))

    state: str = "queued_at_source"
    route_cursor: int = -1
    current_node_id: Optional[str] = None
    current_road_id: Optional[str] = None
    current_lane: Optional[int] = None
    current_cell: int = 0
    desired_road_id: Optional[str] = None
    # next_turn: 'left' | 'straight' | 'right'  – set by engine after routing
    next_turn: str = "straight"
    road_entry_time: float = 0.0
    spawn_time: float = 0.0
    arrival_time: Optional[float] = None
    total_wait_time: float = 0.0
    distance_travelled_m: float = 0.0
    _wait_started_at: Optional[float] = None

    # Vehicle type metadata (set by source)
    type_id: int = 1               # 1–5 vehicle class
    weight: int = 1                # 1–5 size/priority class
    color_override: Optional[str] = None  # per-destination colour set by source

    DESTINATION_COLORS: ClassVar[List[str]] = [
        "#f94144", "#f3722c", "#f8961e", "#90be6d",
        "#43aa8b", "#577590", "#277da1", "#9b5de5",
    ]

    # Type display names
    TYPE_NAMES: ClassVar[List[str]] = [
        "Car", "Auto", "Bus", "Truck", "Bike"
    ]

    def __post_init__(self) -> None:
        self.current_node_id = self.source_id
        self.desired_road_id = self.peek_next_road()

    def begin_wait(self, current_time: float) -> None:
        if self._wait_started_at is None:
            self._wait_started_at = current_time

    def end_wait(self, current_time: float) -> None:
        if self._wait_started_at is not None:
            self.total_wait_time += current_time - self._wait_started_at
            self._wait_started_at = None

    def enter_road(
        self,
        road_id: str,
        lane_index: int,
        current_time: float,
        first_cell: int = 0,
    ) -> None:
        self.end_wait(current_time)
        self.route_cursor += 1
        self.current_road_id = road_id
        self.current_lane = lane_index
        self.current_cell = first_cell
        self.road_entry_time = current_time
        self.state = "on_road"
        self.desired_road_id = self.peek_next_road()

    def advance_within_road(self, lane_index: int, cell_index: int) -> None:
        self.current_lane = lane_index
        self.current_cell = cell_index

    def reach_node(self, node_id: str, current_time: float, travelled_m: float) -> None:
        self.current_node_id = node_id
        self.current_road_id = None
        self.current_lane = None
        self.current_cell = 0
        self.distance_travelled_m += travelled_m
        self.desired_road_id = self.peek_next_road()
        if node_id == self.destination_id:
            self.arrive(current_time)
        else:
            self.state = "queued_at_junction"
            self.begin_wait(current_time)

    def peek_next_road(self) -> Optional[str]:
        next_index = self.route_cursor + 1
        if 0 <= next_index < len(self.route_roads):
            return self.route_roads[next_index]
        return None

    def downstream_target_after_next_entry(self) -> Optional[str]:
        target_index = self.route_cursor + 2
        if 0 <= target_index < len(self.route_roads):
            return self.route_roads[target_index]
        return None

    def movement_label(self) -> str:
        if self.route_cursor < 0:
            return "spawn"
        if self.route_cursor + 1 >= len(self.route_nodes) - 1:
            return "sink"
        prev_node = self.route_nodes[self.route_cursor]
        current_node = self.route_nodes[self.route_cursor + 1]
        next_node = self.route_nodes[self.route_cursor + 2] if self.route_cursor + 2 < len(self.route_nodes) else current_node
        _ = prev_node, next_node
        return "through"

    def arrive(self, current_time: float) -> None:
        self.end_wait(current_time)
        self.arrival_time = current_time
        self.state = "arrived"

    @property
    def color(self) -> str:
        if self.color_override is not None:
            return self.color_override
        return self.DESTINATION_COLORS[hash(self.destination_id) % len(self.DESTINATION_COLORS)]

    @property
    def travel_time(self) -> Optional[float]:
        if self.arrival_time is None:
            return None
        return self.arrival_time - self.spawn_time

    def __repr__(self) -> str:
        return (
            f"Vehicle(id={self.vehicle_id}, src={self.source_id}, dst={self.destination_id}, "
            f"type={self.type_id}, state={self.state}, road={self.current_road_id}, "
            f"lane={self.current_lane}, cell={self.current_cell}, turn={self.next_turn})"
        )