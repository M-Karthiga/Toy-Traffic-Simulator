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
        self.default_min_green = float(min_green)
        self.default_max_green = float(max_green)
        self.yellow_time = float(yellow_time)
        self.service_rate = max(1, int(service_rate))
        self.junction_width = float(junction_width)
        self.junction_height = float(junction_height)

        self.incoming_roads: List[str] = []
        self.outgoing_roads: List[str] = []
        self._current_lane_phase: Optional[Tuple[str, int]] = None
        self._phase_elapsed = 0.0
        self._lane_deficit: Dict[Tuple[str, int], float] = {}

        self.total_processed = 0
        self.total_wait_time = 0.0
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
        states: Dict[str, str] = {}
        for road_id in self.incoming_roads:
            road = roads.get(road_id)
            if road is None:
                continue
            for lane_index in range(road.lanes):
                key = f"{road_id}:{lane_index}"
                states[key] = "GREEN" if self._current_lane_phase == (road_id, lane_index) else "RED"
        return states

    def total_queued(self, roads: Dict[str, object]) -> int:
        return sum(self._lane_queue_length(roads, lane_phase) for lane_phase in self._all_lane_phases(roads))

    def avg_wait_time(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return self.total_wait_time / self.total_processed

    def step(self, dt: float, roads: Dict[str, object], current_time: float) -> List[object]:
        if len(self.incoming_roads) <= 1:
            return self._step_unsignalized(roads, current_time)

        self._phase_elapsed += dt
        moved: List[object] = []

        if self._current_lane_phase is None or self._should_switch(roads):
            self._current_lane_phase = self._pick_next_lane_phase(roads)
            self._phase_elapsed = 0.0

        if self._current_lane_phase is None:
            return moved

        road_id, lane_index = self._current_lane_phase
        road = roads.get(road_id)
        if road is None:
            return moved

        released = 0
        while released < self.service_rate:
            vehicle = road.front_vehicle(lane_index)
            if vehicle is None:
                break

            desired_road_id = vehicle.desired_road_id
            if desired_road_id is None:
                break

            next_road = roads.get(desired_road_id)
            if next_road is None:
                break

            target_lane = next_road.best_entry_lane(vehicle.downstream_target_after_next_entry())
            if target_lane is None:
                break

            popped = road.pop_front_vehicle(lane_index, current_time)
            if popped is None:
                break

            wait_started = popped._wait_started_at
            if wait_started is not None:
                self.total_wait_time += current_time - wait_started

            popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
            if not next_road.accept_vehicle(popped, current_time, preferred_lane=target_lane):
                raise RuntimeError(f"Failed to move vehicle {popped.vehicle_id} across {self.junction_id}")
            moved.append(popped)
            released += 1
            self.total_processed += 1

        self.max_queue = max(self.max_queue, self.total_queued(roads))
        return moved

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
                wait_started = popped._wait_started_at
                if wait_started is not None:
                    self.total_wait_time += current_time - wait_started
                popped.reach_node(self.junction_id, current_time, travelled_m=road.length)
                if not next_road.accept_vehicle(popped, current_time, preferred_lane=target_lane):
                    raise RuntimeError(f"Failed unsignalized move for vehicle {popped.vehicle_id} at {self.junction_id}")
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
        queue_length = self._lane_queue_length(roads, self._current_lane_phase)
        min_green = self.default_min_green
        max_green = self._green_duration_for_lane(roads, self._current_lane_phase)
        if self._phase_elapsed < min_green:
            return False
        if queue_length == 0 and self._phase_elapsed >= self.yellow_time:
            return True
        return self._phase_elapsed >= max_green

    def _green_duration_for_lane(self, roads: Dict[str, object], lane_phase: Tuple[str, int]) -> float:
        queue_length = self._lane_queue_length(roads, lane_phase)
        weight = self._lane_weight(roads, lane_phase)
        if self.signal_algorithm == "fixed":
            return self.default_max_green
        if self.signal_algorithm in {"queue_weighted", "pressure"}:
            return min(self.default_max_green, max(self.default_min_green, self.default_min_green + queue_length * weight))
        if self.signal_algorithm == "wfq_lane":
            return min(self.default_max_green, max(self.default_min_green, self.default_min_green + (queue_length / max(weight, 0.1)) + weight))
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
                self._lane_deficit[best_phase] = max(0.0, self._lane_deficit[best_phase] - self._lane_weight(roads, best_phase))
            return best_phase

        return max(phases, key=lambda lane_phase: self._lane_queue_length(roads, lane_phase) * self._lane_weight(roads, lane_phase))

    def __repr__(self) -> str:
        return f"Junction(id={self.junction_id}, phase={self._current_lane_phase}, processed={self.total_processed})"
