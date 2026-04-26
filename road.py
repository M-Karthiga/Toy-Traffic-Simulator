"""Directional multi-lane road cells with safe discrete-time movement."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple


class Road:
    """
    A directional road represented by per-lane occupancy cells.

    Each cell holds at most one vehicle, so overlaps cannot happen.
    Vehicles stop at the final cell, which acts as a stop line before the junction.
    """

    def __init__(
        self,
        road_id: str,
        from_node: str,
        to_node: str,
        length: float = 120.0,
        speed_limit: float = 12.0,
        lanes: int = 1,
        cell_length: float = 7.5,
        lane_directions: Optional[Sequence[Sequence[str]]] = None,
        lane_flow_weights: Optional[Sequence[float]] = None,
        corridor_id: Optional[str] = None,
        stop_line_offset: int = 1,
    ) -> None:
        self.road_id = road_id
        self.from_node = from_node
        self.to_node = to_node
        self.length = float(length)
        self.speed_limit = float(speed_limit)
        self.lanes = max(1, int(lanes))
        self.cell_length = float(cell_length)
        self.stop_line_offset = max(1, int(stop_line_offset))
        self.corridor_id = corridor_id

        self.cell_count = max(3, int(math.ceil(self.length / self.cell_length)))
        self.capacity = self.cell_count * self.lanes
        self.stop_cell = self.cell_count - 1
        self._occupancy: List[List[Optional[object]]] = [
            [None for _ in range(self.cell_count)] for _ in range(self.lanes)
        ]

        self.lane_directions: List[List[str]] = self._normalise_lane_directions(lane_directions)
        self.lane_flow_weights: List[float] = self._normalise_lane_flow_weights(lane_flow_weights)

        self.total_vehicles_entered = 0
        self.total_vehicles_exited = 0
        self.cumulative_travel_time = 0.0
        self.max_occupancy = 0

    def _normalise_lane_directions(self, lane_directions: Optional[Sequence[Sequence[str]]]) -> List[List[str]]:
        if not lane_directions:
            return [["*"] for _ in range(self.lanes)]
        result: List[List[str]] = []
        for index in range(self.lanes):
            if index < len(lane_directions):
                allowed = [str(item) for item in lane_directions[index]] or ["*"]
            else:
                allowed = ["*"]
            result.append(allowed)
        return result

    def _normalise_lane_flow_weights(self, lane_flow_weights: Optional[Sequence[float]]) -> List[float]:
        values = [float(value) for value in (lane_flow_weights or [])]
        while len(values) < self.lanes:
            values.append(1.0)
        return values[: self.lanes]

    @property
    def occupancy(self) -> int:
        return sum(1 for lane in self._occupancy for vehicle in lane if vehicle is not None)

    def utilisation(self) -> float:
        return self.occupancy / self.capacity if self.capacity else 0.0

    def lane_can_accept(self, lane_index: int) -> bool:
        return 0 <= lane_index < self.lanes and self._occupancy[lane_index][0] is None

    def allowed_lanes_for(self, desired_road_id: Optional[str]) -> List[int]:
        allowed_lanes: List[int] = []
        for lane_index, lane_rules in enumerate(self.lane_directions):
            if "*" in lane_rules or desired_road_id in lane_rules or not lane_rules:
                allowed_lanes.append(lane_index)
        return allowed_lanes

    def best_entry_lane(self, desired_road_id: Optional[str]) -> Optional[int]:
        candidate_lanes = self.allowed_lanes_for(desired_road_id)
        free_candidates = [lane for lane in candidate_lanes if self.lane_can_accept(lane)]
        if not free_candidates:
            return None
        return min(free_candidates, key=lambda lane: self._lane_density(lane))

    def can_accept_vehicle(self, desired_road_id: Optional[str] = None) -> bool:
        return self.best_entry_lane(desired_road_id) is not None

    def accept_vehicle(self, vehicle, current_time: float, preferred_lane: Optional[int] = None) -> bool:
        if preferred_lane is not None and self.lane_can_accept(preferred_lane):
            lane_index = preferred_lane
        else:
            lane_index = self.best_entry_lane(vehicle.downstream_target_after_next_entry())
        if lane_index is None:
            return False

        self._occupancy[lane_index][0] = vehicle
        vehicle.enter_road(self.road_id, lane_index, current_time, first_cell=0)
        self.total_vehicles_entered += 1
        self.max_occupancy = max(self.max_occupancy, self.occupancy)
        return True

    def movement_probability(self, dt: float, lane_index: int) -> float:
        density = self._lane_density(lane_index)
        free_flow_probability = min(0.92, (self.speed_limit * dt) / self.cell_length)
        congestion_factor = max(0.2, 1.0 - 0.6 * density)
        return max(0.05, min(0.98, free_flow_probability * congestion_factor))

    def _lane_density(self, lane_index: int) -> float:
        return sum(1 for vehicle in self._occupancy[lane_index] if vehicle is not None) / max(1, self.cell_count)

    def lane_vehicle_count(self, lane_index: int) -> int:
        return sum(1 for vehicle in self._occupancy[lane_index] if vehicle is not None)

    def front_vehicle(self, lane_index: int):
        vehicle = self._occupancy[lane_index][self.stop_cell]
        if vehicle is not None:
            return vehicle
        return None

    def pop_front_vehicle(self, lane_index: int, current_time: float):
        vehicle = self._occupancy[lane_index][self.stop_cell]
        if vehicle is None:
            return None
        self._occupancy[lane_index][self.stop_cell] = None
        self.total_vehicles_exited += 1
        self.cumulative_travel_time += current_time - vehicle.road_entry_time
        return vehicle

    def step(self, dt: float, rng) -> None:
        for lane_index in range(self.lanes):
            move_probability = self.movement_probability(dt, lane_index)

            for cell_index in range(self.stop_cell - 1, -1, -1):
                vehicle = self._occupancy[lane_index][cell_index]
                if vehicle is None:
                    continue

                target_lane, target_cell = self._choose_next_position(vehicle, lane_index, cell_index, rng, move_probability)
                if target_lane == lane_index and target_cell == cell_index:
                    continue

                self._occupancy[lane_index][cell_index] = None
                self._occupancy[target_lane][target_cell] = vehicle
                vehicle.advance_within_road(target_lane, target_cell)

        self.max_occupancy = max(self.max_occupancy, self.occupancy)

    def _choose_next_position(
        self,
        vehicle,
        lane_index: int,
        cell_index: int,
        rng,
        move_probability: float,
    ) -> Tuple[int, int]:
        current_allowed = self._lane_allows_turn(lane_index, vehicle.desired_road_id)
        candidate_moves: List[Tuple[int, int, float]] = []
        approach_cells = 4
        near_stop_line = cell_index >= self.stop_cell - approach_cells

        if cell_index + 1 <= self.stop_cell and self._occupancy[lane_index][cell_index + 1] is None:
            candidate_moves.append((lane_index, cell_index + 1, 1.0 if current_allowed else 0.5))

        if near_stop_line:
            if candidate_moves and rng.random() < move_probability:
                candidate_moves.sort(key=lambda move: (move[2], move[1]), reverse=True)
                best_lane, best_cell, _ = candidate_moves[0]
                return best_lane, best_cell
            return lane_index, cell_index

        for lane_shift in (-1, 1):
            next_lane = lane_index + lane_shift
            if not 0 <= next_lane < self.lanes:
                continue
            if self._occupancy[next_lane][cell_index] is not None:
                continue
            if not self._lane_allows_turn(next_lane, vehicle.desired_road_id):
                continue
            if current_allowed and self._lane_density(next_lane) >= self._lane_density(lane_index):
                continue
            weight = 1.3 if cell_index >= self.stop_cell - 3 else 0.7
            candidate_moves.append((next_lane, cell_index, weight))
            if cell_index + 1 <= self.stop_cell and self._occupancy[next_lane][cell_index + 1] is None:
                candidate_moves.append((next_lane, cell_index + 1, weight + 0.3))

        if not candidate_moves or rng.random() >= move_probability:
            return lane_index, cell_index

        candidate_moves.sort(key=lambda move: (move[2], move[1]), reverse=True)
        best_lane, best_cell, _ = candidate_moves[0]
        return best_lane, best_cell

    def _lane_allows_turn(self, lane_index: int, desired_road_id: Optional[str]) -> bool:
        lane_rules = self.lane_directions[lane_index]
        return "*" in lane_rules or desired_road_id in lane_rules or desired_road_id is None

    def avg_travel_time(self) -> float:
        if self.total_vehicles_exited == 0:
            return 0.0
        return self.cumulative_travel_time / self.total_vehicles_exited

    def vehicle_positions(self) -> Dict[int, Tuple[float, float]]:
        positions: Dict[int, Tuple[float, float]] = {}
        cell_denominator = max(1, self.cell_count - 1)
        lane_denominator = max(1, self.lanes - 1)
        for lane_index, lane in enumerate(self._occupancy):
            lateral = 0.5 if self.lanes == 1 else lane_index / lane_denominator
            for cell_index, vehicle in enumerate(lane):
                if vehicle is not None:
                    longitudinal = cell_index / cell_denominator
                    positions[vehicle.vehicle_id] = (longitudinal, lateral)
        return positions

    def lane_signal_state(self, lane_index: int, signal_states: Dict[str, str]) -> str:
        return signal_states.get(f"{self.road_id}:{lane_index}", signal_states.get(self.road_id, "RED"))

    def __repr__(self) -> str:
        return (
            f"Road(id={self.road_id}, from={self.from_node}, to={self.to_node}, "
            f"lanes={self.lanes}, occ={self.occupancy}/{self.capacity})"
        )
