"""Directional multi-lane road cells with safe discrete-time movement.

Lane assignment – Indian left-keep rule
----------------------------------------
For multi-lane roads (lanes >= 2), explicit lane_directions[] is IGNORED.
Instead, a vehicle's desired turn at the next junction determines which lane it
should be in:
  • Left turn  → lane 0  (leftmost / kerb lane)
  • Straight   → middle  (lane 1 … n-2)
  • Right turn → lane n-1 (rightmost / fast lane)

Single-lane roads still use lane_directions=["*"] (wildcard, no config needed).

Vehicles approaching the stop line (within APPROACH_CELLS) do NOT change lane,
mirroring real stop-line queuing behaviour.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple


APPROACH_CELLS = 5   # cells from stop-line where lane changes are forbidden


class Road:
    """
    A directional road represented by per-lane occupancy cells.

    Each cell holds at most one vehicle, so overlaps cannot happen.
    Vehicles stop at the final cell (stop_cell), which is the stop line
    before the junction. They are rendered just short of the junction box.
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
        stop_line_offset: int = 2,
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
        self.stop_cell = max(1, self.cell_count - 1 - self.stop_line_offset)
        self._occupancy: List[List[Optional[object]]] = [
            [None for _ in range(self.cell_count)] for _ in range(self.lanes)
        ]

        # lane_directions kept for single-lane roads or explicit overrides.
        # Multi-lane roads use Indian rule via preferred_lanes_for_turn().
        self.lane_directions: List[List[str]] = self._normalise_lane_directions(lane_directions)
        self.lane_flow_weights: List[float] = self._normalise_lane_flow_weights(lane_flow_weights)

        self.total_vehicles_entered = 0
        self.total_vehicles_exited = 0
        self.cumulative_travel_time = 0.0
        self.max_occupancy = 0

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Indian left-keep lane helpers
    # ------------------------------------------------------------------

    def preferred_lanes_for_turn(self, turn: str) -> List[int]:
        """Return preferred lane indices for the given turn at road end.

        turn: 'left' | 'straight' | 'right'
        Lane 0 = leftmost (kerb), lane n-1 = rightmost (centre/fast).
        """
        n = self.lanes
        if n == 1:
            return [0]
        if turn == "left":
            return [0]
        if turn == "right":
            return [n - 1]
        # straight: middle lanes, falling back to all if no middle exists
        middle = list(range(1, n - 1))
        return middle if middle else [0, n - 1]

    def allowed_lanes_for(self, desired_road_id: Optional[str],
                          turn: str = "straight") -> List[int]:
        """Return lanes legal for the given next-road / turn combination.

        Multi-lane roads (lanes >= 2): use Indian turn rule.
        Single-lane roads: use lane_directions wildcard (always [0]).
        """
        if self.lanes == 1:
            return [0]
        preferred = self.preferred_lanes_for_turn(turn)
        # Fall back to all lanes if preferred are all occupied
        return preferred

    # ------------------------------------------------------------------
    # Capacity / entry helpers
    # ------------------------------------------------------------------

    @property
    def occupancy(self) -> int:
        return sum(1 for lane in self._occupancy for vehicle in lane if vehicle is not None)

    def utilisation(self) -> float:
        return self.occupancy / self.capacity if self.capacity else 0.0

    def lane_can_accept(self, lane_index: int) -> bool:
        return 0 <= lane_index < self.lanes and self._occupancy[lane_index][0] is None

    def best_entry_lane(self, desired_road_id: Optional[str],
                        turn: str = "straight") -> Optional[int]:
        """Pick the best free lane for a vehicle entering this road.

        Preferred lanes are determined by the Indian rule using *turn*.
        Falls back to any free lane if preferred lanes are full.
        """
        preferred = self.allowed_lanes_for(desired_road_id, turn)
        free_preferred = [l for l in preferred if self.lane_can_accept(l)]
        if free_preferred:
            return min(free_preferred, key=lambda l: self._lane_density(l))
        # Fallback: any free lane
        any_free = [l for l in range(self.lanes) if self.lane_can_accept(l)]
        if any_free:
            return min(any_free, key=lambda l: self._lane_density(l))
        return None

    def can_accept_vehicle(self, desired_road_id: Optional[str] = None) -> bool:
        return self.best_entry_lane(desired_road_id) is not None

    def accept_vehicle(self, vehicle, current_time: float,
                       preferred_lane: Optional[int] = None) -> bool:
        if preferred_lane is not None and self.lane_can_accept(preferred_lane):
            lane_index = preferred_lane
        else:
            turn = getattr(vehicle, "next_turn", "straight")
            lane_index = self.best_entry_lane(
                getattr(vehicle, "desired_road_id", None), turn
            )
        if lane_index is None:
            return False

        self._occupancy[lane_index][0] = vehicle
        vehicle.enter_road(self.road_id, lane_index, current_time, first_cell=0)
        self.total_vehicles_entered += 1
        self.max_occupancy = max(self.max_occupancy, self.occupancy)
        return True

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def movement_probability(self, dt: float, lane_index: int) -> float:
        density = self._lane_density(lane_index)
        free_flow_probability = min(0.92, (self.speed_limit * dt) / self.cell_length)
        congestion_factor = max(0.2, 1.0 - 0.6 * density)
        return max(0.05, min(0.98, free_flow_probability * congestion_factor))

    def _lane_density(self, lane_index: int) -> float:
        return sum(1 for v in self._occupancy[lane_index] if v is not None) / max(1, self.cell_count)

    def lane_vehicle_count(self, lane_index: int) -> int:
        return sum(1 for v in self._occupancy[lane_index] if v is not None)

    def front_vehicle(self, lane_index: int):
        return self._occupancy[lane_index][self.stop_cell]

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
            move_prob = self.movement_probability(dt, lane_index)
            for cell_index in range(self.stop_cell - 1, -1, -1):
                vehicle = self._occupancy[lane_index][cell_index]
                if vehicle is None:
                    continue
                target_lane, target_cell = self._choose_next_position(
                    vehicle, lane_index, cell_index, rng, move_prob
                )
                if target_lane == lane_index and target_cell == cell_index:
                    continue
                # GUARD: never move into an occupied cell
                if self._occupancy[target_lane][target_cell] is not None:
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
        near_stop_line = cell_index >= self.stop_cell - APPROACH_CELLS
        current_turn = getattr(vehicle, "next_turn", "straight")
        preferred_for_turn = self.preferred_lanes_for_turn(current_turn)
        already_correct = lane_index in preferred_for_turn

        candidate_moves: List[Tuple[int, int, float]] = []

        # Move forward in same lane
        if cell_index + 1 <= self.stop_cell and self._occupancy[lane_index][cell_index + 1] is None:
            candidate_moves.append((lane_index, cell_index + 1, 1.0))

        # Near stop-line: no lane changes
        if near_stop_line:
            if candidate_moves and rng.random() < move_probability:
                return lane_index, cell_index + 1
            return lane_index, cell_index

        # Lane changes only when not already in correct lane
        if not already_correct:
            for lane_shift in (-1, 1):
                next_lane = lane_index + lane_shift
                if not 0 <= next_lane < self.lanes:
                    continue
                # STRICT: both target cell AND current cell in target lane must be free
                if self._occupancy[next_lane][cell_index] is not None:
                    continue
                if cell_index + 1 <= self.stop_cell and self._occupancy[next_lane][cell_index + 1] is not None:
                    pass  # forward cell blocked, only lateral move available
                if next_lane not in preferred_for_turn:
                    continue
                weight = 1.5
                candidate_moves.append((next_lane, cell_index, weight))
                if (cell_index + 1 <= self.stop_cell
                        and self._occupancy[next_lane][cell_index + 1] is None):
                    candidate_moves.append((next_lane, cell_index + 1, weight + 0.3))
        
        if not candidate_moves or rng.random() >= move_probability:
            return lane_index, cell_index

        candidate_moves.sort(key=lambda m: (m[2], m[1]), reverse=True)
        return candidate_moves[0][0], candidate_moves[0][1]

    def _lane_allows_turn(self, lane_index: int, desired_road_id: Optional[str]) -> bool:
        """Legacy helper kept for compatibility."""
        lane_rules = self.lane_directions[lane_index]
        return "*" in lane_rules or desired_road_id in lane_rules or desired_road_id is None

    def avg_travel_time(self) -> float:
        if self.total_vehicles_exited == 0:
            return 0.0
        return self.cumulative_travel_time / self.total_vehicles_exited

    def vehicle_positions(self) -> Dict[int, Tuple[float, float]]:
        """Return {vehicle_id: (longitudinal_fraction, lane_index)}.
        
        Returns raw lane_index (not a 0-1 fraction) so _point_along_road
        can place each lane at the correct physical offset.
        """
        positions: Dict[int, Tuple[float, float]] = {}
        cell_denominator = max(1, self.cell_count - 1)
        stop_fraction = max(0.0, (self.stop_cell - 0.5) / cell_denominator)

        for lane_index, lane in enumerate(self._occupancy):
            for cell_index, vehicle in enumerate(lane):
                if vehicle is not None:
                    longitudinal = stop_fraction if cell_index == self.stop_cell \
                        else cell_index / cell_denominator
                    # Return raw lane_index — engine converts to pixel offset
                    positions[vehicle.vehicle_id] = (longitudinal, float(lane_index))
        return positions

    def lane_signal_state(self, lane_index: int, signal_states: Dict[str, str]) -> str:
        return signal_states.get(f"{self.road_id}:{lane_index}",
                                 signal_states.get(self.road_id, "RED"))

    def __repr__(self) -> str:
        return (
            f"Road(id={self.road_id}, from={self.from_node}, to={self.to_node}, "
            f"lanes={self.lanes}, occ={self.occupancy}/{self.capacity})"
        )
