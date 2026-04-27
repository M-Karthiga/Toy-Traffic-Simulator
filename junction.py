"""Signalized junction controller with lane-level weighted fair queueing."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


class Junction:
    """A junction with lane-level signals and adaptive green allocation."""

    def __init__(
        self,
        junction_id: str,
        pos: tuple = (0.0, 0.0),
        signal_algorithm: str = "wfq_lane",
        phases: Optional[List[dict]] = None,
        min_green: float = 4.0,
        max_green: float = 12.0,
        yellow_time: float = 1.0,
        service_rate: int = 1,
        junction_width: float = 58.0,
        junction_height: float = 58.0,
    ) -> None:
        self.junction_id = junction_id
        self.pos = tuple(pos)
        self.signal_algorithm = signal_algorithm
        self.phases = list(phases or [])
        self.default_min_green = max(10.0, float(min_green))
        self.default_max_green = max(15.0, float(max_green), self.default_min_green)
        self.yellow_time = max(2.0, float(yellow_time))
        self.service_rate = max(1, int(service_rate))
        self.junction_width = float(junction_width)
        self.junction_height = float(junction_height)
        self.is_source: bool = False
        self.is_sink: bool = False
        self.incoming_roads: List[str] = []
        self.outgoing_roads: List[str] = []
        self._current_lane_phase: Optional[Tuple[str, int]] = None
        self._current_phase_group: List[Tuple[str, int]] = []
        self._phase_elapsed = 0.0
        self._lane_deficit: Dict[Tuple[str, int], float] = {}

        self.total_processed = 0
        self.max_queue = 0

    def add_incoming_road(self, road_id: str) -> None:
        if road_id not in self.incoming_roads:
            self.incoming_roads.append(road_id)

    def add_outgoing_road(self, road_id: str) -> None:
        if road_id not in self.outgoing_roads:
            self.outgoing_roads.append(road_id)

    @property
    def current_green(self) -> Optional[str]:
        if self._current_lane_phase is None:
            return None
        road_id, _lane = self._current_lane_phase
        return road_id

    def signal_states(self, roads: Dict[str, object]) -> Dict[str, str]:
        if len(self.incoming_roads) <= 1:
            return {}
        green_set = set(self._current_phase_group) if self._current_phase_group else (
            {self._current_lane_phase} if self._current_lane_phase else set()
        )
        states: Dict[str, str] = {}
        for road_id in self.incoming_roads:
            road = roads.get(road_id)
            if road is None:
                continue
            for lane_index in range(road.lanes):
                key = f"{road_id}:{lane_index}"
                states[key] = "GREEN" if (road_id, lane_index) in green_set else "RED"
        return states

    def get_signal_for_lane(self, road_id: str, lane_index: int) -> str:
        """Return 'GREEN' or 'RED' for a specific incoming lane at this junction."""
        if len(self.incoming_roads) <= 1:
            return "GREEN"
        if self._current_phase_group:
            return "GREEN" if (road_id, lane_index) in self._current_phase_group else "RED"
        if self._current_lane_phase == (road_id, lane_index):
            return "GREEN"
        return "RED"

    def total_queued(self, roads: Dict[str, object]) -> int:
        return sum(self._lane_queue_length(roads, lane_phase) for lane_phase in self._all_lane_phases(roads))

    def step(self, dt: float, roads: Dict[str, object], current_time: float) -> List[object]:
        if len(self.incoming_roads) <= 1:
            return self._step_unsignalized(roads, current_time)

        self._phase_elapsed += dt
        moved: List[object] = []

        # Use Indian grouped-phase scheduling (N-S together, E-W together, etc.)
        if self._current_lane_phase is None or self._should_switch(roads):
            self._current_lane_phase = self._pick_next_lane_phase(roads)
            self._current_phase_group = self._get_phase_group(self._current_lane_phase, roads)
            self._phase_elapsed = 0.0

        if self._current_lane_phase is None:
            return moved

        # Serve all lanes in the current phase group simultaneously.
        active_lanes = self._current_phase_group if self._current_phase_group else [self._current_lane_phase]
        for road_id, lane_index in active_lanes:
            road = roads.get(road_id)
            if road is None:
                continue
            for _ in range(self.service_rate):
                vehicle = road.front_vehicle(lane_index)
                if vehicle is None:
                    break
                desired_road_id = vehicle.desired_road_id
                if desired_road_id is None:
                    popped = road.pop_front_vehicle(lane_index, current_time)
                    if popped is None:
                        break
                    popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
                    moved.append(popped)
                    self.total_processed += 1
                    continue

                next_road = roads.get(desired_road_id)
                if next_road is None:
                    break
                target_lane = next_road.best_entry_lane(vehicle.downstream_target_after_next_entry())
                if target_lane is None:
                    break

                popped = road.pop_front_vehicle(lane_index, current_time)
                if popped is None:
                    break
                popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
                if not next_road.accept_vehicle(popped, current_time, preferred_lane=target_lane):
                    road._occupancy[lane_index][road.stop_cell] = popped
                    break
                moved.append(popped)
                self.total_processed += 1

        self.max_queue = max(self.max_queue, self.total_queued(roads))
        return moved

    def _get_phase_group(
        self,
        lead_phase: Optional[Tuple[str, int]],
        roads: Dict[str, object],
    ) -> List[Tuple[str, int]]:
        """Return all (road_id, lane) pairs that are on the same axis as lead_phase."""
        if lead_phase is None:
            return []
        lead_road_id, _ = lead_phase
        lead_road = roads.get(lead_road_id)
        if lead_road is None:
            return [lead_phase]

        lead_angle = self._road_bearing(lead_road)
        group: List[Tuple[str, int]] = []
        for road_id in self.incoming_roads:
            road = roads.get(road_id)
            if road is None:
                continue
            angle = self._road_bearing(road)
            diff = abs((angle - lead_angle + 180) % 360 - 180)
            if diff <= 45 or diff >= 135:
                for lane_index in range(road.lanes):
                    group.append((road_id, lane_index))
        return group if group else [lead_phase]

    def _road_bearing(self, road) -> float:
        """Bearing in degrees of the road direction toward this junction."""
        import math

        jx, jy = self.pos
        try:
            fx = getattr(road, "_from_x", None)
            fy = getattr(road, "_from_y", None)
            if fx is None or fy is None:
                return 0.0
            dx = jx - fx
            dy = jy - fy
            return math.degrees(math.atan2(dy, dx)) % 360
        except Exception:
            return 0.0

    def _step_unsignalized(self, roads: Dict[str, object], current_time: float) -> List[object]:
        moved: List[object] = []
        for road_id in self.incoming_roads:
            road = roads.get(road_id)
            if road is None:
                continue
            for lane_index in range(road.lanes):
                vehicle = road.front_vehicle(lane_index)
                if vehicle is None:
                    continue
                desired_road_id = vehicle.desired_road_id
                if desired_road_id is None:
                    popped = road.pop_front_vehicle(lane_index, current_time)
                    if popped is not None:
                        popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
                        moved.append(popped)
                        self.total_processed += 1
                    continue

                next_road = roads.get(desired_road_id)
                if next_road is None:
                    continue
                target_lane = next_road.best_entry_lane(vehicle.downstream_target_after_next_entry())
                if target_lane is None:
                    continue

                popped = road.pop_front_vehicle(lane_index, current_time)
                if popped is None:
                    continue
                popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
                if not next_road.accept_vehicle(popped, current_time, preferred_lane=target_lane):
                    road._occupancy[lane_index][road.stop_cell] = popped
                    continue
                moved.append(popped)
                self.total_processed += 1

        self.max_queue = max(self.max_queue, self.total_queued(roads))
        return moved

    def _all_lane_phases(self, roads: Dict[str, object]) -> List[Tuple[str, int]]:
        phases: List[Tuple[str, int]] = []
        for road_id in self.incoming_roads:
            road = roads.get(road_id)
            if road is None:
                continue
            for lane_index in range(road.lanes):
                phases.append((road_id, lane_index))
        return phases

    def _lane_queue_length(self, roads: Dict[str, object], lane_phase: Tuple[str, int]) -> int:
        road_id, lane_index = lane_phase
        road = roads.get(road_id)
        if road is None:
            return 0
        return road.lane_vehicle_count(lane_index)

    def _lane_weight(self, roads: Dict[str, object], lane_phase: Tuple[str, int]) -> float:
        road_id, lane_index = lane_phase
        road = roads.get(road_id)
        if road is None:
            return 1.0
        return road.lane_flow_weights[lane_index]

    def _should_switch(self, roads: Dict[str, object]) -> bool:
        if self._current_lane_phase is None:
            return True
        if self.total_queued(roads) == 0:
            return False
        queue_length = self._phase_group_queue_length(roads)
        min_green = self.default_min_green
        max_green = self._green_duration_for_lane(roads, self._current_lane_phase)
        if self._phase_elapsed < min_green:
            return False
        if queue_length == 0 and self._phase_elapsed >= self.yellow_time:
            return True
        return self._phase_elapsed >= max_green

    def _phase_group_queue_length(self, roads: Dict[str, object]) -> int:
        active_lanes = self._current_phase_group if self._current_phase_group else (
            [self._current_lane_phase] if self._current_lane_phase else []
        )
        return sum(self._lane_queue_length(roads, lane_phase) for lane_phase in active_lanes)

    def _green_duration_for_lane(self, roads: Dict[str, object], lane_phase: Tuple[str, int]) -> float:
        queue_length = self._lane_queue_length(roads, lane_phase)
        weight = self._lane_weight(roads, lane_phase)
        if self.signal_algorithm == "fixed":
            return self.default_max_green
        if self.signal_algorithm in {"queue_weighted", "pressure"}:
            return min(
                self.default_max_green,
                max(self.default_min_green, self.default_min_green + queue_length * weight),
            )
        if self.signal_algorithm == "wfq_lane":
            return min(
                self.default_max_green,
                max(self.default_min_green, self.default_min_green + (queue_length / max(weight, 0.1)) + weight),
            )
        return self.default_max_green

    def _pick_next_lane_phase(self, roads: Dict[str, object]) -> Optional[Tuple[str, int]]:
        phases = self._all_lane_phases(roads)
        if not phases:
            return None

        if self.signal_algorithm == "wfq_lane":
            best_phase = None
            best_score = float("-inf")
            for lane_phase in phases:
                queue_length = self._lane_queue_length(roads, lane_phase)
                weight = self._lane_weight(roads, lane_phase)
                self._lane_deficit[lane_phase] = self._lane_deficit.get(lane_phase, 0.0) + queue_length * weight
                score = self._lane_deficit[lane_phase]
                if score > best_score:
                    best_score = score
                    best_phase = lane_phase
            if best_phase is not None:
                self._lane_deficit[best_phase] = max(
                    0.0,
                    self._lane_deficit[best_phase] - self._lane_weight(roads, best_phase),
                )
            return best_phase

        return max(
            phases,
            key=lambda lane_phase: self._lane_queue_length(roads, lane_phase) * self._lane_weight(roads, lane_phase),
        )

    def __repr__(self) -> str:
        return f"Junction(id={self.junction_id}, phase={self._current_lane_phase}, processed={self.total_processed})"
