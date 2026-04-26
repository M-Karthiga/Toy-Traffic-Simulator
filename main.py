"""Run the assignment traffic simulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import SimulationEngine
from netedit import DEFAULT_NETWORK, NetworkEditor, apply_network_to_engine, load_network_definition, save_network_definition
from visualiser import Visualiser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mini SUMO-style traffic simulator")
    parser.add_argument("--duration", type=float, default=180.0, help="Simulation duration in seconds")
    parser.add_argument("--dt", type=float, default=1.0, help="Simulation time step")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--network", type=str, default="", help="Path to a JSON network file")
    parser.add_argument("--edit", action="store_true", help="Launch the lightweight net editor")
    parser.add_argument("--export-demo", type=str, default="", help="Export the built-in editable demo network to JSON and exit")
    parser.add_argument("--output-dir", type=str, default="outputs", help="Directory for JSON, GIF, and PNG outputs")
    parser.add_argument("--fps", type=int, default=12, help="Animation frames per second")
    return parser.parse_args()


def load_or_create_network(args: argparse.Namespace) -> dict:
    if args.export_demo:
        save_network_definition(DEFAULT_NETWORK, args.export_demo)
        print(f"Demo network exported to {args.export_demo}")
        raise SystemExit(0)

    if args.edit:
        editor = NetworkEditor(args.network or "network.json")
        editor.run()
        raise SystemExit(0)

    if args.network:
        return load_network_definition(args.network)
    return DEFAULT_NETWORK


def main() -> None:
    args = parse_args()
    network = load_or_create_network(args)

    engine = SimulationEngine(dt=args.dt, seed=args.seed)
    apply_network_to_engine(engine, network)
    engine.build()

    print("=" * 68)
    print("Mini SUMO-Style Traffic Simulator")
    print("=" * 68)
    print(f"Nodes: {len(network['nodes'])}   Roads: {len(network['roads'])}")
    print(f"Running for {args.duration:.0f}s with dt={args.dt:.2f}s")

    def progress(current: float, end: float) -> None:
        ratio = current / end if end else 1.0
        blocks = int(30 * ratio)
        bar = "#" * blocks + "-" * (30 - blocks)
        print(f"\r[{bar}] {ratio * 100:5.1f}%   t={current:6.1f}s", end="", flush=True)

    engine.run(duration=args.duration, snapshot_interval=max(args.dt, 1.0), progress_callback=progress)
    print()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = engine.statistics()
    stats_path = output_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    visualiser = Visualiser(engine, output=str(output_dir / "simulation.gif"), fps=args.fps)
    try:
        visualiser.render()
        visualiser.plot_statistics(str(output_dir / "statistics.png"))
    except RuntimeError as exc:
        print(f"Visual outputs skipped: {exc}")

    print("\nSummary")
    print("-" * 68)
    print(f"Vehicles created : {stats['total_vehicles']}")
    print(f"Vehicles arrived : {stats['arrived_vehicles']}")
    print(f"Peak active      : {stats['max_active_vehicles']}")
    print(f"Avg travel time  : {stats['avg_travel_time_s']:.2f}s")
    print(f"Avg wait time    : {stats['avg_wait_time_s']:.2f}s")
    print(f"Throughput       : {stats['throughput_veh_per_s']:.3f} veh/s")
    print(f"Outputs          : {output_dir.resolve()}")


if __name__ == "__main__":
    main()
