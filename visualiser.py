"""Static and animated visualisation for the traffic simulator."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import List

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.animation as animation
    import matplotlib.pyplot as plt
    from matplotlib import patches, transforms
    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    animation = None
    plt = None
    patches = None
    transforms = None
    MATPLOTLIB_AVAILABLE = False


ROAD_SURFACE = "#8d8d8d"
ROAD_EDGE = "#5f5f5f"
BACKGROUND = "#efe8dd"
JUNCTION_COLOR = "#274c77"
SOURCE_COLOR = "#4caf50"
SINK_COLOR = "#e76f51"
TEXT_COLOR = "#222222"


class Visualiser:
    """Renders a flat top-down animation with simple rectangular vehicles."""

    def __init__(self, engine, output: str = "simulation.gif", fps: int = 12, dpi: int = 100, max_frames: int = 240) -> None:
        self.engine = engine
        self.output = output
        self.fps = fps
        self.dpi = dpi
        self.max_frames = max_frames

    def render(self) -> None:
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("matplotlib is required to render GIF or MP4 output.")
        if not self.engine.snapshots:
            return

        Path(self.output).parent.mkdir(parents=True, exist_ok=True)
        frames = self.engine.snapshots
        step = max(1, len(frames) // self.max_frames)
        frames = frames[::step]

        fig, ax = plt.subplots(figsize=(10, 7), facecolor=BACKGROUND)
        ax.set_facecolor(BACKGROUND)
        ax.axis("off")

        xs, ys = self._all_positions()
        ax.set_xlim(min(xs) - 80, max(xs) + 80)
        ax.set_ylim(max(ys) + 80, min(ys) - 80)
        ax.set_aspect("equal")

        self._draw_static_map(ax)
        time_text = ax.text(0.02, 0.96, "", transform=ax.transAxes, color=TEXT_COLOR, fontsize=11, va="top")
        queue_text = ax.text(0.02, 0.91, "", transform=ax.transAxes, color=TEXT_COLOR, fontsize=9, va="top")
        vehicle_artists: List[patches.Patch] = []

        def update(frame):
            nonlocal vehicle_artists
            for artist in vehicle_artists:
                artist.remove()
            vehicle_artists = []

            for vehicle in frame["vehicles"]:
                vehicle_artists.extend(self._draw_vehicle(ax, vehicle))

            time_text.set_text(
                f"t = {frame['time']:.0f}s   active = {frame['active']}   arrived = {frame['arrived']}"
            )
            queues = ", ".join(f"{jid}:{size}" for jid, size in frame["junction_queues"].items())
            queue_text.set_text(f"junction queues: {queues}")
            vehicle_artists.extend(self._draw_signals(ax, frame.get("signals", {})))
            return vehicle_artists + [time_text, queue_text]

        ani = animation.FuncAnimation(fig, update, frames=frames, interval=1000 / self.fps, blit=True)
        ext = os.path.splitext(self.output)[1].lower()
        if ext == ".mp4":
            ani.save(self.output, writer=animation.FFMpegWriter(fps=self.fps), dpi=self.dpi)
        else:
            ani.save(self.output, writer=animation.PillowWriter(fps=self.fps), dpi=self.dpi)
        plt.close(fig)

    def plot_statistics(self, output: str = "statistics.png") -> None:
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("matplotlib is required to render statistics plots.")
        stats = self.engine.statistics()
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), facecolor=BACKGROUND)
        fig.suptitle("Traffic Simulation Dashboard", fontsize=16, color=TEXT_COLOR)

        for ax in axes.flat:
            ax.set_facecolor("#f7f2ea")
            for spine in ax.spines.values():
                spine.set_color("#c7bba7")
            ax.tick_params(colors=TEXT_COLOR)

        road_ids = list(stats["roads"].keys())
        road_utils = [stats["roads"][road_id]["utilisation"] for road_id in road_ids]
        axes[0, 0].barh(road_ids, road_utils, color="#577590")
        axes[0, 0].set_title("Road Utilisation", color=TEXT_COLOR)
        axes[0, 0].set_xlim(0, 1)

        junction_ids = list(stats["junctions"].keys())
        junction_queues = [stats["junctions"][junction_id]["current_queue"] for junction_id in junction_ids]
        axes[0, 1].bar(junction_ids, junction_queues, color="#f8961e")
        axes[0, 1].set_title("Current Junction Queue", color=TEXT_COLOR)

        sink_ids = list(stats["sinks"].keys())
        sink_arrivals = [stats["sinks"][sink_id]["arrived"] for sink_id in sink_ids]
        axes[1, 0].bar(sink_ids, sink_arrivals, color="#90be6d")
        axes[1, 0].set_title("Arrivals Per Sink", color=TEXT_COLOR)

        axes[1, 1].axis("off")
        summary = (
            f"Simulation time: {stats['simulation_time']:.0f}s\n"
            f"Vehicles created: {stats['total_vehicles']}\n"
            f"Vehicles arrived: {stats['arrived_vehicles']}\n"
            f"Avg travel time: {stats['avg_travel_time_s']:.2f}s\n"
            f"Avg wait time: {stats['avg_wait_time_s']:.2f}s\n"
            f"Throughput: {stats['throughput_veh_per_s']:.3f} veh/s\n"
            f"Peak active vehicles: {stats['max_active_vehicles']}"
        )
        axes[1, 1].text(0.05, 0.95, summary, transform=axes[1, 1].transAxes, va="top", fontsize=12, color=TEXT_COLOR)

        Path(output).parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(output, dpi=self.dpi, facecolor=BACKGROUND)
        plt.close(fig)

    def _draw_static_map(self, ax) -> None:
        drawn_corridors = set()
        for road in self.engine.roads.values():
            corridor_id = getattr(road, "corridor_id", None)
            if corridor_id:
                if corridor_id in drawn_corridors:
                    continue
                paired = [candidate for candidate in self.engine.roads.values() if getattr(candidate, "corridor_id", None) == corridor_id]
                if len(paired) == 2:
                    self._draw_bidirectional_corridor(ax, paired[0], paired[1])
                    drawn_corridors.add(corridor_id)
                    continue
            start = self._node_pos(road.from_node)
            end = self._node_pos(road.to_node)
            road_width = 6 + road.lanes * 4
            ax.plot([start[0], end[0]], [start[1], end[1]], color=ROAD_EDGE, linewidth=road_width + 3, solid_capstyle="butt", zorder=1)
            ax.plot([start[0], end[0]], [start[1], end[1]], color=ROAD_SURFACE, linewidth=road_width, solid_capstyle="butt", zorder=2)
            ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color=ROAD_EDGE, lw=1.6), zorder=3)
            self._draw_lane_markers(ax, start, end, road.lanes)

        for source in self.engine.sources.values():
            ax.add_patch(patches.Rectangle((source.pos[0] - 12, source.pos[1] - 12), 24, 24, facecolor=SOURCE_COLOR, edgecolor="#1f5122", zorder=4))
            ax.text(source.pos[0], source.pos[1] + 26, source.source_id, ha="center", fontsize=9, color=TEXT_COLOR)

        for sink in self.engine.sinks.values():
            ax.add_patch(patches.RegularPolygon(sink.pos, numVertices=4, radius=15, orientation=math.pi / 4, facecolor=SINK_COLOR, edgecolor="#7a2d1b", zorder=4))
            ax.text(sink.pos[0], sink.pos[1] + 26, sink.sink_id, ha="center", fontsize=9, color=TEXT_COLOR)

        for junction in self.engine.junctions.values():
            width = getattr(junction, "junction_width", 60) * 0.28
            height = getattr(junction, "junction_height", 60) * 0.28
            ax.add_patch(
                patches.Rectangle(
                    (junction.pos[0] - width / 2, junction.pos[1] - height / 2),
                    width,
                    height,
                    facecolor=JUNCTION_COLOR,
                    edgecolor="#15253a",
                    zorder=4,
                )
            )
            ax.text(junction.pos[0], junction.pos[1] + 26, junction.junction_id, ha="center", fontsize=9, color=TEXT_COLOR)

    def _draw_bidirectional_corridor(self, ax, road_a, road_b) -> None:
        start = self._node_pos(road_a.from_node)
        end = self._node_pos(road_a.to_node)
        total_lanes = road_a.lanes + road_b.lanes
        road_width = 8 + total_lanes * 4
        ax.plot([start[0], end[0]], [start[1], end[1]], color=ROAD_EDGE, linewidth=road_width + 4, solid_capstyle="butt", zorder=1)
        ax.plot([start[0], end[0]], [start[1], end[1]], color=ROAD_SURFACE, linewidth=road_width, solid_capstyle="butt", zorder=2)
        self._draw_lane_markers(ax, start, end, total_lanes)
        mid_start = _offset_point(start, end, 0.0, 0.0)
        mid_end = _offset_point(end, start, 0.0, 0.0)
        ax.plot([mid_start[0], mid_end[0]], [mid_start[1], mid_end[1]], color="#f4d35e", linewidth=1.8, zorder=2.7)
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color=ROAD_EDGE, lw=1.2), zorder=3)
        ax.annotate("", xy=start, xytext=end, arrowprops=dict(arrowstyle="-|>", color=ROAD_EDGE, lw=1.2), zorder=3)

    def _draw_lane_markers(self, ax, start: tuple, end: tuple, lanes: int) -> None:
        if lanes <= 1:
            return
        for lane_index in range(1, lanes):
            offset = lane_index - lanes / 2
            start_offset = _offset_point(start, end, offset, 7.0)
            end_offset = _offset_point(end, start, -offset, 7.0)
            ax.plot(
                [start_offset[0], end_offset[0]],
                [start_offset[1], end_offset[1]],
                color="#d8d8d8",
                linewidth=1.0,
                linestyle="--",
                zorder=2.5,
            )

    def _draw_vehicle(self, ax, vehicle: dict) -> List[patches.Patch]:
        body = patches.Rectangle((vehicle["x"] - 7, vehicle["y"] - 4), 14, 8, facecolor=vehicle["color"], edgecolor="#1b1b1b", linewidth=1.0, zorder=6)
        transform = transforms.Affine2D().rotate_deg_around(vehicle["x"], vehicle["y"], vehicle["angle"]) + ax.transData
        body.set_transform(transform)

        wheel1 = patches.Rectangle((vehicle["x"] - 5, vehicle["y"] - 5.5), 3, 1.5, facecolor="#111111", edgecolor="none", zorder=7)
        wheel2 = patches.Rectangle((vehicle["x"] + 2, vehicle["y"] - 5.5), 3, 1.5, facecolor="#111111", edgecolor="none", zorder=7)
        wheel3 = patches.Rectangle((vehicle["x"] - 5, vehicle["y"] + 4.0), 3, 1.5, facecolor="#111111", edgecolor="none", zorder=7)
        wheel4 = patches.Rectangle((vehicle["x"] + 2, vehicle["y"] + 4.0), 3, 1.5, facecolor="#111111", edgecolor="none", zorder=7)
        for wheel in (wheel1, wheel2, wheel3, wheel4):
            wheel.set_transform(transform)

        ax.add_patch(body)
        ax.add_patch(wheel1)
        ax.add_patch(wheel2)
        ax.add_patch(wheel3)
        ax.add_patch(wheel4)
        return [body, wheel1, wheel2, wheel3, wheel4]

    def _node_pos(self, node_id: str) -> tuple:
        if node_id in self.engine.sources:
            return self.engine.sources[node_id].pos
        if node_id in self.engine.junctions:
            return self.engine.junctions[node_id].pos
        if node_id in self.engine.sinks:
            return self.engine.sinks[node_id].pos
        return (0.0, 0.0)

    def _all_positions(self) -> tuple:
        xs = []
        ys = []
        for source in self.engine.sources.values():
            xs.append(source.pos[0])
            ys.append(source.pos[1])
        for junction in self.engine.junctions.values():
            xs.append(junction.pos[0])
            ys.append(junction.pos[1])
        for sink in self.engine.sinks.values():
            xs.append(sink.pos[0])
            ys.append(sink.pos[1])
        return xs or [0, 100], ys or [0, 100]

    def _draw_signals(self, ax, signal_states: dict) -> List[patches.Patch]:
        artists: List[patches.Patch] = []
        for junction_id, states in signal_states.items():
            junction = self.engine.junctions.get(junction_id)
            if junction is None:
                continue
            for road_id in junction.incoming_roads:
                road = self.engine.roads.get(road_id)
                if road is None:
                    continue
                start = self._node_pos(road.from_node)
                end = self._node_pos(road.to_node)
                for lane_index in range(road.lanes):
                    sx = end[0] - (end[0] - start[0]) * 0.14
                    sy = end[1] - (end[1] - start[1]) * 0.14
                    sx, sy = _offset_point((sx, sy), start, lane_index - (road.lanes - 1) / 2, 7.0)
                    color = "#2ecc71" if states.get(f"{road_id}:{lane_index}") == "GREEN" else "#e63946"
                    light = patches.Circle((sx, sy), radius=2.8, facecolor=color, edgecolor="#111111", zorder=8)
                    ax.add_patch(light)
                    artists.append(light)
        return artists


def _offset_point(start: tuple, end: tuple, lane_offset: float, spacing: float) -> tuple:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    return start[0] + nx * lane_offset * spacing, start[1] + ny * lane_offset * spacing
