"""Source and sink nodes for the traffic simulator."""

from __future__ import annotations

import collections
import random
from typing import Deque, Dict, Iterable, List, Optional


class Source:
    """Generates vehicles and buffers them when the outgoing road is blocked."""

    def __init__(
        self,
        source_id: str,
        pos: tuple = (0.0, 0.0),
        rate: float = 0.25,
        mode: str = "poisson",
        destinations: Optional[Iterable[str]] = None,
        destination_weights: Optional[Dict[str, float]] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.source_id = source_id
        self.pos = tuple(pos)
        self.rate = float(rate)
        self.mode = mode
        self.destinations = list(destinations or [])
        self.destination_weights = dict(destination_weights or {})
        self.outgoing_roads: List[str] = []
        self.pending_vehicles: Deque[object] = collections.deque()
        self.total_generated = 0
        self.total_released = 0

        self._rng = random.Random(seed)
        self._next_arrival = self._sample_gap()
        self._constant_timer = 0.0

    def add_outgoing_road(self, road_id: str) -> None:
        if road_id not in self.outgoing_roads:
            self.outgoing_roads.append(road_id)

    def _sample_gap(self) -> float:
        if self.rate <= 0:
            return float("inf")
        if self.mode == "constant":
            return 1.0 / self.rate
        return self._rng.expovariate(self.rate)

    def _pick_destination(self) -> Optional[str]:
        if not self.destinations:
            return None
        if self.destination_weights:
            weights = [self.destination_weights.get(dest, 1.0) for dest in self.destinations]
            return self._rng.choices(self.destinations, weights=weights, k=1)[0]
        return self._rng.choice(self.destinations)

    def step(self, dt: float) -> List[str]:
        spawned: List[str] = []
        if self.rate <= 0:
            return spawned

        if self.mode == "constant":
            self._constant_timer += dt
            gap = self._sample_gap()
            while self._constant_timer >= gap:
                self._constant_timer -= gap
                destination = self._pick_destination()
                if destination is not None:
                    spawned.append(destination)
        else:
            self._next_arrival -= dt
            while self._next_arrival <= 0:
                destination = self._pick_destination()
                if destination is not None:
                    spawned.append(destination)
                self._next_arrival += self._sample_gap()

        self.total_generated += len(spawned)
        return spawned

    def queue_vehicle(self, vehicle) -> None:
        self.pending_vehicles.append(vehicle)

    def dequeue_vehicle(self):
        if self.pending_vehicles:
            vehicle = self.pending_vehicles.popleft()
            self.total_released += 1
            return vehicle
        return None

    def __repr__(self) -> str:
        return f"Source(id={self.source_id}, generated={self.total_generated}, queued={len(self.pending_vehicles)})"


class Sink:
    """Absorbs arriving vehicles and records completion statistics."""

    def __init__(self, sink_id: str, pos: tuple = (0.0, 0.0)) -> None:
        self.sink_id = sink_id
        self.pos = tuple(pos)
        self.incoming_roads: List[str] = []
        self.total_arrived = 0
        self.total_travel_time = 0.0
        self.arrived_vehicle_ids: List[int] = []

    def add_incoming_road(self, road_id: str) -> None:
        if road_id not in self.incoming_roads:
            self.incoming_roads.append(road_id)

    def receive_vehicle(self, vehicle, current_time: float) -> None:
        vehicle.arrive(current_time)
        self.total_arrived += 1
        self.arrived_vehicle_ids.append(vehicle.vehicle_id)
        if vehicle.spawn_time is not None:
            self.total_travel_time += current_time - vehicle.spawn_time

    def avg_travel_time(self) -> float:
        if self.total_arrived == 0:
            return 0.0
        return self.total_travel_time / self.total_arrived

    def __repr__(self) -> str:
        return f"Sink(id={self.sink_id}, arrived={self.total_arrived})"
