"""Core simulation engine."""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional

try:
    from .junction import Junction
    from .road import Road
    from .router import Router
    from .source_sink import Sink, Source
    from .vehicle import Vehicle
except ImportError:  # pragma: no cover
    from junction import Junction
    from road import Road
    from router import Router
    from source_sink import Sink, Source
    from vehicle import Vehicle


class SimulationEngine:
    """Discrete-time traffic simulation over roads and junctions."""

    def __init__(self, dt: float = 1.0, seed: int = 42) -> None:
        self.dt = float(dt)
        self.seed = int(seed)
        self.time = 0.0
        self.random = random.Random(seed)

        self.roads: Dict[str, Road] = {}
        self.junctions: Dict[str, Junction] = {}
        self.sources: Dict[str, Source] = {}
        self.sinks: Dict[str, Sink] = {}

        self.router = Router()

        self._built = False
        self._vehicles_all: List[Vehicle] = []
        self._vehicles_active: Dict[int, Vehicle] = {}
        self._vehicles_arrived: List[Vehicle] = []
        self.snapshots: List[dict] = []

        self.max_active_vehicles = 0

    def add_road(self, road: Road) -> None:
        self.roads[road.road_id] = road

    def add_junction(self, junction: Junction) -> None:
        self.junctions[junction.junction_id] = junction

    def add_source(self, source: Source) -> None:
        self.sources[source.source_id] = source

    def add_sink(self, sink: Sink) -> None:
        self.sinks[sink.sink_id] = sink

    def build(self) -> None:
        for road in self.roads.values():
            from_id = road.from_node
            to_id = road.to_node

            # from_node wiring
            if from_id in self.sources:
                self.sources[from_id].add_outgoing_road(road.road_id)
            if from_id in self.junctions:
                self.junctions[from_id].add_outgoing_road(road.road_id)

            # to_node wiring
            if to_id in self.sinks:
                self.sinks[to_id].add_incoming_road(road.road_id)
            if to_id in self.junctions:
                self.junctions[to_id].add_incoming_road(road.road_id)

        node_ids = list(self.sources) + list(self.junctions) + list(self.sinks)
        # Deduplicate: a junction-source-sink node appears in multiple lists
        node_ids = list(dict.fromkeys(node_ids))
        self.router.build_from_network(self.roads, node_ids)
        self._built = True
        
    def run(
        self,
        duration: float,
        snapshot_interval: float = 1.0,
        progress_callback: Optional[Callable[[float, float], None]] = None,
    ) -> None:
        if not self._built:
            self.build()

        end_time = self.time + duration
        next_snapshot = self.time
        self._record_snapshot()

        while self.time < end_time:
            self._step()
            if self.time >= next_snapshot:
                self._record_snapshot()
                next_snapshot += snapshot_interval
            if progress_callback:
                progress_callback(self.time, end_time)

    def _step(self) -> None:
        self._spawn_and_release_from_sources()

        for road in self.roads.values():
            road.step(self.dt, self.random)

        self._drain_terminal_roads()

        for junction in self.junctions.values():
            junction.step(self.dt, self.roads, self.time + self.dt)

        self.time += self.dt
        self.max_active_vehicles = max(self.max_active_vehicles, len(self._vehicles_active))

    def _spawn_and_release_from_sources(self) -> None:
        for source in self.sources.values():
            spawned_list = source.step(self.dt)
            for spawn in spawned_list:
                # Support both legacy str and new dict formats
                if isinstance(spawn, str):
                    destination_id = spawn
                    type_id, weight, color_override = 1, 1, None
                else:
                    destination_id = spawn["destination"]
                    type_id = spawn.get("type_id", 1)
                    weight = spawn.get("weight", 1)
                    color_override = spawn.get("color", None)

                route = self.router.plan_route(source.source_id, destination_id)
                if route is None:
                    continue
                route_nodes, route_roads = route
                vehicle = Vehicle(
                    source_id=source.source_id,
                    destination_id=destination_id,
                    route_nodes=route_nodes,
                    route_roads=route_roads,
                    type_id=type_id,
                    weight=weight,
                    color_override=color_override,
                )
                vehicle.spawn_time = self.time
                vehicle.begin_wait(self.time)
                source.queue_vehicle(vehicle)
                self._vehicles_all.append(vehicle)
                self._vehicles_active[vehicle.vehicle_id] = vehicle

            if not source.pending_vehicles:
                continue

            vehicle = source.pending_vehicles[0]
            first_road_id = vehicle.peek_next_road()
            if first_road_id is None:
                source.dequeue_vehicle()
                vehicle.arrive(self.time)
                self._mark_arrived(vehicle)
                continue

            road = self.roads.get(first_road_id)
            if road is not None and road.accept_vehicle(vehicle, self.time):
                source.dequeue_vehicle()


    def _mark_arrived(self, vehicle: Vehicle) -> None:
        if vehicle.vehicle_id in self._vehicles_active:
            self._vehicles_active.pop(vehicle.vehicle_id)
        self._vehicles_arrived.append(vehicle)

    def _drain_terminal_roads(self) -> None:
        current_time = self.time + self.dt
        for road in self.roads.values():
            to_node = road.to_node
            # Drain into sink if to_node is a pure sink OR a junction that also acts as sink
            is_terminal = to_node in self.sinks
            if not is_terminal:
                continue
            # If to_node is also a junction (source+sink junction), only drain vehicles
            # whose destination IS this node (others pass through junction step normally)
            is_also_junction = to_node in self.junctions
            for lane_index in range(road.lanes):
                vehicle = road.front_vehicle(lane_index)
                if vehicle is None:
                    continue
                if is_also_junction and vehicle.destination_id != to_node:
                    # Let the junction step handle routing this vehicle onward
                    continue
                popped = road.pop_front_vehicle(lane_index, current_time)
                if popped is None:
                    continue
                popped.reach_node(to_node, current_time, travelled_m=road.length)
                self.sinks[to_node].receive_vehicle(popped, current_time)
                self._mark_arrived(popped)

    def _node_position(self, node_id: str) -> tuple:
        if node_id in self.sources:
            return self.sources[node_id].pos
        if node_id in self.junctions:
            return self.junctions[node_id].pos
        if node_id in self.sinks:
            return self.sinks[node_id].pos
        return (0.0, 0.0)

    def _record_snapshot(self) -> None:
        vehicle_entries = []
        signal_states = {
            junction_id: junction.signal_states(self.roads)
            for junction_id, junction in self.junctions.items()
        }

        for road in self.roads.values():
            positions = road.vehicle_positions()
            start_x, start_y = self._node_position(road.from_node)
            end_x, end_y = self._node_position(road.to_node)
            for vehicle_id, (fraction, lateral) in positions.items():
                vehicle = self._vehicles_active.get(vehicle_id)
                if vehicle is None:
                    continue
                x, y = _point_along_road((start_x, start_y), (end_x, end_y), fraction, lateral, road.lanes)
                vehicle_entries.append(
                    {
                        "id": vehicle.vehicle_id,
                        "x": x,
                        "y": y,
                        "angle": _angle_between((start_x, start_y), (end_x, end_y)),
                        "color": vehicle.color,
                        "state": vehicle.state,
                        "destination": vehicle.destination_id,
                    }
                )

        for source in self.sources.values():
            for offset, vehicle in enumerate(list(source.pending_vehicles)[:6]):
                x, y = source.pos
                vehicle_entries.append(
                    {
                        "id": vehicle.vehicle_id,
                        "x": x - 16 * (offset + 1),
                        "y": y - 12,
                        "angle": 0.0,
                        "color": vehicle.color,
                        "state": "queued_at_source",
                        "destination": vehicle.destination_id,
                    }
                )

        self.snapshots.append(
            {
                "time": self.time,
                "vehicles": vehicle_entries,
                "junction_queues": {jid: junction.total_queued(self.roads) for jid, junction in self.junctions.items()},
                "signals": signal_states,
                "active": len(self._vehicles_active),
                "arrived": len(self._vehicles_arrived),
            }
        )

    def statistics(self) -> dict:
        arrived_travel_times = [vehicle.travel_time for vehicle in self._vehicles_arrived if vehicle.travel_time is not None]
        all_wait_times = [vehicle.total_wait_time for vehicle in self._vehicles_all]

        return {
            "simulation_time": self.time,
            "total_vehicles": len(self._vehicles_all),
            "active_vehicles": len(self._vehicles_active),
            "arrived_vehicles": len(self._vehicles_arrived),
            "max_active_vehicles": self.max_active_vehicles,
            "avg_travel_time_s": sum(arrived_travel_times) / len(arrived_travel_times) if arrived_travel_times else 0.0,
            "avg_wait_time_s": sum(all_wait_times) / len(all_wait_times) if all_wait_times else 0.0,
            "throughput_veh_per_s": (len(self._vehicles_arrived) / self.time) if self.time else 0.0,
            "roads": {
                road_id: {
                    "from": road.from_node,
                    "to": road.to_node,
                    "utilisation": road.utilisation(),
                    "avg_travel_time_s": road.avg_travel_time(),
                    "entered": road.total_vehicles_entered,
                    "exited": road.total_vehicles_exited,
                    "max_occupancy": road.max_occupancy,
                }
                for road_id, road in self.roads.items()
            },
            "junctions": {
                junction_id: {
                    "processed": junction.total_processed,
                    "avg_wait_time_s": junction.avg_wait_time(),
                    "max_queue": junction.max_queue,
                    "current_queue": junction.total_queued(self.roads),
                    "green_incoming": junction.current_green,
                    "phases": junction.phases,
                    "algorithm": junction.signal_algorithm,
                }
                for junction_id, junction in self.junctions.items()
            },
            "sources": {
                source_id: {
                    "generated": source.total_generated,
                    "released": source.total_released,
                    "pending": len(source.pending_vehicles),
                }
                for source_id, source in self.sources.items()
            },
            "sinks": {
                sink_id: {
                    "arrived": sink.total_arrived,
                    "avg_travel_time_s": sink.avg_travel_time(),
                }
                for sink_id, sink in self.sinks.items()
            },
        }


def _angle_between(start: tuple, end: tuple) -> float:
    import math

    return math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))


def _point_along_road(start: tuple, end: tuple, fraction: float, lateral: float, lane_count: int) -> tuple:
    import math

    x = start[0] + (end[0] - start[0]) * fraction
    y = start[1] + (end[1] - start[1]) * fraction
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    lane_span = (lane_count - 1) * 7.0
    offset = (lateral - 0.5) * lane_span
    return x + nx * offset, y + ny * offset
