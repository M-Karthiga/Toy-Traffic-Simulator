"""User-friendly network editor and network loader."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None

try:
    from .junction import Junction
    from .road import Road
    from .source_sink import Sink, Source
except ImportError:  # pragma: no cover
    from junction import Junction
    from road import Road
    from source_sink import Sink, Source


DEFAULT_NETWORK = {
    "meta": {"name": "junction-role-demo"},
    "nodes": [
        {
            "id": "J1",
            "x": 120,
            "y": 240,
            "is_source": True,
            "is_sink": False,
            "source_rate": 0.35,
            "source_mode": "poisson",
            "destinations": ["J5", "J6"],
            "destination_weights": {"J5": 1.0, "J6": 1.0},
            "signal_algorithm": "wfq_lane",
            "min_green": 4,
            "max_green": 12,
            "service_rate": 1,
            "junction_width": 54,
            "junction_height": 54,
        },
        {
            "id": "J2",
            "x": 320,
            "y": 120,
            "is_source": True,
            "is_sink": False,
            "source_rate": 0.25,
            "source_mode": "poisson",
            "destinations": ["J5", "J6"],
            "destination_weights": {"J5": 2.0, "J6": 1.0},
            "signal_algorithm": "wfq_lane",
            "min_green": 4,
            "max_green": 12,
            "service_rate": 1,
            "junction_width": 54,
            "junction_height": 54,
        },
        {
            "id": "J3",
            "x": 320,
            "y": 240,
            "is_source": False,
            "is_sink": False,
            "signal_algorithm": "wfq_lane",
            "min_green": 5,
            "max_green": 14,
            "service_rate": 1,
            "junction_width": 64,
            "junction_height": 64,
        },
        {
            "id": "J4",
            "x": 320,
            "y": 360,
            "is_source": False,
            "is_sink": False,
            "signal_algorithm": "wfq_lane",
            "min_green": 5,
            "max_green": 14,
            "service_rate": 1,
            "junction_width": 64,
            "junction_height": 64,
        },
        {
            "id": "J5",
            "x": 540,
            "y": 240,
            "is_source": False,
            "is_sink": True,
            "signal_algorithm": "wfq_lane",
            "min_green": 4,
            "max_green": 10,
            "service_rate": 1,
            "junction_width": 54,
            "junction_height": 54,
        },
        {
            "id": "J6",
            "x": 540,
            "y": 420,
            "is_source": False,
            "is_sink": True,
            "signal_algorithm": "wfq_lane",
            "min_green": 4,
            "max_green": 10,
            "service_rate": 1,
            "junction_width": 54,
            "junction_height": 54,
        },
    ],
    "roads": [
        {
            "id": "R1A",
            "from": "J1",
            "to": "J3",
            "length": 200,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["R3A", "R4A"], ["R3A"]],
            "lane_flow_weights": [1.0, 1.5],
            "corridor_id": "C1",
        },
        {
            "id": "R1B",
            "from": "J3",
            "to": "J1",
            "length": 200,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["*"], ["*"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C1",
        },
        {
            "id": "R2A",
            "from": "J2",
            "to": "J3",
            "length": 120,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["R3A", "R4A"], ["R4A"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C2",
        },
        {
            "id": "R2B",
            "from": "J3",
            "to": "J2",
            "length": 120,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["*"], ["*"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C2",
        },
        {
            "id": "R3A",
            "from": "J3",
            "to": "J5",
            "length": 220,
            "speed_limit": 12,
            "lanes": 2,
            "lane_directions": [["*"], ["*"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C3",
        },
        {
            "id": "R3B",
            "from": "J5",
            "to": "J3",
            "length": 220,
            "speed_limit": 12,
            "lanes": 2,
            "lane_directions": [["*"], ["*"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C3",
        },
        {
            "id": "R4A",
            "from": "J3",
            "to": "J4",
            "length": 120,
            "speed_limit": 10,
            "lanes": 2,
            "lane_directions": [["R6A"], ["R6A"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C4",
        },
        {
            "id": "R4B",
            "from": "J4",
            "to": "J3",
            "length": 120,
            "speed_limit": 10,
            "lanes": 2,
            "lane_directions": [["R1B", "R2B"], ["R2B"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C4",
        },
        {
            "id": "R6A",
            "from": "J4",
            "to": "J6",
            "length": 220,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["*"], ["*"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C5",
        },
        {
            "id": "R6B",
            "from": "J6",
            "to": "J4",
            "length": 220,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["R4B"], ["R4B"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C5",
        },
        {
            "id": "R7A",
            "from": "J1",
            "to": "J2",
            "length": 200,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["R2A"], ["R2A"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C6",
        },
        {
            "id": "R7B",
            "from": "J2",
            "to": "J1",
            "length": 200,
            "speed_limit": 11,
            "lanes": 2,
            "lane_directions": [["R1A"], ["R1A"]],
            "lane_flow_weights": [1.0, 1.0],
            "corridor_id": "C6",
        },
    ],
}


def save_network_definition(network_data: dict, path: str) -> None:
    Path(path).write_text(json.dumps(network_data, indent=2), encoding="utf-8")


def load_network_definition(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_network_to_engine(engine, network_data: dict) -> None:
    sink_ids = {
        node["id"]
        for node in network_data.get("nodes", [])
        if node.get("is_sink") or node.get("kind") == "sink"
    }
    for node in network_data.get("nodes", []):
        pos = (node["x"], node["y"])
        node_id = node["id"]
        is_source = node.get("is_source") or node.get("kind") == "source"
        is_sink = node.get("is_sink") or node.get("kind") == "sink"
        raw_vehicle_types = list(node.get("vehicle_types", []))
        valid_vehicle_types = [vt for vt in raw_vehicle_types if vt.get("destination") in sink_ids and vt.get("destination") != node_id]
        valid_destinations = [dest for dest in node.get("destinations", []) if dest in sink_ids and dest != node_id]
        valid_destination_weights = {
            dest: weight for dest, weight in node.get("destination_weights", {}).items()
            if dest in sink_ids and dest != node_id
        }
        engine.add_junction(
            Junction(
                junction_id=node_id,
                pos=pos,
                signal_algorithm=node.get("signal_algorithm", "wfq_lane"),
                phases=node.get("phases", []),
                min_green=node.get("min_green", 4.0),
                max_green=node.get("max_green", 12.0),
                yellow_time=node.get("yellow_time", 1.0),
                service_rate=node.get("service_rate", 1),
                junction_width=node.get("junction_width", 58),
                junction_height=node.get("junction_height", 58),
            )
        )
        if is_source:
            engine.add_source(
                Source(
                    source_id=node_id,
                    pos=pos,
                    rate=node.get("source_rate", node.get("rate", 0.25)),
                    mode=node.get("source_mode", node.get("mode", "poisson")),
                    destinations=valid_destinations,
                    destination_weights=valid_destination_weights,
                    vehicle_types=valid_vehicle_types,
                )
            
            )
        if is_sink:
            engine.add_sink(Sink(sink_id=node_id, pos=pos))

    for road in network_data.get("roads", []):
        engine.add_road(
            Road(
                road_id=road["id"],
                from_node=road["from"],
                to_node=road["to"],
                length=road.get("length", 120),
                speed_limit=road.get("speed_limit", 12),
                lanes=road.get("lanes", 1),
                cell_length=road.get("cell_length", 7.5),
                lane_directions=road.get("lane_directions"),
                lane_flow_weights=road.get("lane_flow_weights"),
                corridor_id=road.get("corridor_id"),
            )
        )


class NetworkEditor:
    """Form-based junction and lane editor."""

    def __init__(self, json_path: str = "network.json") -> None:
        if tk is None:
            raise RuntimeError("tkinter is required for the editor GUI.")

        self.json_path = str(json_path)
        self.network = json.loads(json.dumps(DEFAULT_NETWORK))
        self.mode = "select"
        self.selected_kind: Optional[str] = None
        self.selected_id: Optional[str] = None
        self.draw_start_node: Optional[str] = None
        self.dragging_node_id: Optional[str] = None

        self.root = tk.Tk()
        self.root.title("Traffic NetEdit")
        self.root.geometry("1180x760")

        self.main = tk.Frame(self.root, bg="#efe8dd")
        self.main.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.main, width=820, height=760, bg="#f7f2ea", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.sidebar = tk.Frame(self.main, width=360, bg="#ded5c4")
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.status = tk.StringVar(value="Select mode")
        tk.Label(self.root, textvariable=self.status, anchor="w", bg="#f7f2ea").pack(fill=tk.X, side=tk.BOTTOM)

        self._build_toolbar()
        self._build_sidebar()
        self._bind_canvas()
        self._load_if_exists()
        self._redraw()

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self.canvas, bg="#d8c8aa")
        toolbar.place(x=10, y=10)
        buttons = [
            ("Select", "select"),
            ("Junction", "junction"),
            ("Draw Road", "road"),
            ("Save", "save"),
            ("Open", "open"),
            ("Demo", "demo"),
        ]
        for label, action in buttons:
            tk.Button(toolbar, text=label, width=9, command=lambda a=action: self._toolbar_action(a)).pack(side=tk.LEFT, padx=2, pady=3)

    def _build_sidebar(self) -> None:
        title = tk.Label(self.sidebar, text="Inspector", font=("Arial", 15, "bold"), bg="#ded5c4")
        title.pack(anchor="w", padx=12, pady=(12, 4))

        self.object_name = tk.StringVar(value="No selection")
        tk.Label(self.sidebar, textvariable=self.object_name, bg="#ded5c4", font=("Arial", 11, "bold")).pack(anchor="w", padx=12)

        # Scrollable area
        scroll_container = tk.Frame(self.sidebar, bg="#ded5c4")
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._scroll_canvas = tk.Canvas(scroll_container, bg="#ded5c4", highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_container, orient="vertical", command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.form = tk.Frame(self._scroll_canvas, bg="#ded5c4")
        self._form_window = self._scroll_canvas.create_window((0, 0), window=self.form, anchor="nw")

        def _on_frame_configure(event):
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
        def _on_canvas_configure(event):
            self._scroll_canvas.itemconfig(self._form_window, width=event.width)
        self.form.bind("<Configure>", _on_frame_configure)
        self._scroll_canvas.bind("<Configure>", _on_canvas_configure)
        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._build_node_form()
        self._build_road_form()
        self._show_form(None)

    def _build_node_form(self) -> None:
        self.node_form = tk.Frame(self.form, bg="#ded5c4")

        # ── Core state vars ──────────────────────────────────────────
        self.node_id_var          = tk.StringVar()
        self.node_source_var      = tk.BooleanVar(value=False)
        self.node_sink_var        = tk.BooleanVar(value=False)
        self.node_source_rate_var = tk.StringVar(value="0.00")  # computed/display only
        self.node_signal_algo_var = tk.StringVar(value="wfq_lane")
        self.node_min_green_var   = tk.StringVar(value="4")
        self.node_max_green_var   = tk.StringVar(value="12")
        self.node_service_var     = tk.StringVar(value="1")
        self.node_size_var        = tk.StringVar(value="60")

        # ── Basic info ───────────────────────────────────────────────
        basic = tk.Frame(self.node_form, bg="#ded5c4")
        basic.pack(fill=tk.X, padx=6, pady=(4, 0))

        tk.Label(basic, text="Junction ID", bg="#ded5c4", font=("Arial", 9, "bold")).pack(anchor="w")
        tk.Entry(basic, textvariable=self.node_id_var).pack(fill=tk.X, pady=(0, 6))

        roles_frame = tk.LabelFrame(basic, text="Role", bg="#ded5c4", font=("Arial", 9, "bold"))
        roles_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Checkbutton(roles_frame, text="Acts as Source  (generates vehicles)",
                       variable=self.node_source_var, bg="#ded5c4",
                       command=self._on_role_changed).pack(anchor="w", padx=4)
        tk.Checkbutton(roles_frame, text="Acts as Sink  (absorbs vehicles)",
                       variable=self.node_sink_var, bg="#ded5c4",
                       command=self._on_role_changed).pack(anchor="w", padx=4)

        # Source rate display (sum of vehicle type rates)
        rate_row = tk.Frame(basic, bg="#ded5c4")
        rate_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(rate_row, text="Total Source Rate:", bg="#ded5c4", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(rate_row, textvariable=self.node_source_rate_var, bg="#ded5c4",
                 fg="#1a4a1a", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=4)
        tk.Label(rate_row, text="veh/s", bg="#ded5c4", font=("Arial", 8)).pack(side=tk.LEFT)

        # Junction size
        tk.Label(basic, text="Junction Size (px)", bg="#ded5c4").pack(anchor="w")
        tk.Entry(basic, textvariable=self.node_size_var).pack(fill=tk.X, pady=(0, 6))

        # ── Tabbed notebook: Source Config + Advanced ─────────────────
        try:
            import tkinter.ttk as ttk
            nb = ttk.Notebook(self.node_form)
        except Exception:
            nb = None

        if nb is not None:
            self._src_tab  = tk.Frame(nb, bg="#ded5c4")
            self._adv_tab  = tk.Frame(nb, bg="#ded5c4")
            nb.add(self._src_tab,  text=" Vehicle Types ")
            nb.add(self._adv_tab,  text=" Advanced ")
            nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            self._nb = nb
        else:
            # Fallback: no ttk — use plain frames
            self._src_tab = tk.LabelFrame(self.node_form, text="Vehicle Types", bg="#ded5c4")
            self._src_tab.pack(fill=tk.X, padx=4, pady=4)
            self._adv_tab = tk.LabelFrame(self.node_form, text="Advanced", bg="#ded5c4")
            self._adv_tab.pack(fill=tk.X, padx=4, pady=4)
            self._nb = None

        # ── Source / Vehicle-types tab ───────────────────────────────
        DEST_COLORS = ["#e53935", "#43a047", "#1e88e5", "#fb8c00", "#8e24aa"]
        self._vtype_rows = []
        src_scroll_frame = tk.Frame(self._src_tab, bg="#ded5c4")
        src_scroll_frame.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(src_scroll_frame, bg="#ded5c4")
        hdr.pack(fill=tk.X, padx=4, pady=(4, 0))
        tk.Label(hdr, text="#", bg="#ded5c4", width=2, font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="Destination", bg="#ded5c4", width=10, font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=2)
        tk.Label(hdr, text="Rate (0–2 veh/s)", bg="#ded5c4", width=14, font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=2)
        tk.Label(hdr, text="Wt", bg="#ded5c4", width=3, font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=2)

        for vt_idx in range(5):
            row = tk.Frame(src_scroll_frame, bg="#ded5c4")
            row.pack(fill=tk.X, padx=4, pady=2)
            swatch = tk.Label(row, bg=DEST_COLORS[vt_idx], width=2, relief="ridge")
            swatch.pack(side=tk.LEFT, padx=(0, 3))

            dest_var = tk.StringVar(value="")
            flow_var = tk.StringVar(value="0.0")
            wt_var   = tk.StringVar(value=str(vt_idx + 1))

            # Destination: OptionMenu (dropdown); choices refreshed when loading selection
            dest_om = tk.OptionMenu(row, dest_var, "")
            dest_om.config(width=7, bg="#f5f0e8")
            dest_om.pack(side=tk.LEFT, padx=2)

            tk.Entry(row, textvariable=flow_var, width=6).pack(side=tk.LEFT, padx=2)
            tk.Entry(row, textvariable=wt_var, width=3).pack(side=tk.LEFT, padx=2)

            self._vtype_rows.append({
                "dest": dest_var, "flow": flow_var, "weight": wt_var,
                "swatch": swatch, "color": DEST_COLORS[vt_idx],
                "dest_om": dest_om,
            })

            # Recompute total rate whenever flow changes
            flow_var.trace_add("write", lambda *_: self._refresh_source_rate_display())

        # ── Advanced tab ─────────────────────────────────────────────
        adv = self._adv_tab
        self.signal_controls_frame = tk.Frame(adv, bg="#ded5c4")
        self.signal_controls_frame.pack(fill=tk.X, padx=0, pady=0)
        tk.Label(self.signal_controls_frame, text="Signal Algorithm", bg="#ded5c4", font=("Arial", 9)).pack(anchor="w", padx=6, pady=(6, 0))
        algo_menu = tk.OptionMenu(self.signal_controls_frame, self.node_signal_algo_var,
                                  "wfq_lane", "fixed", "queue_weighted", "pressure")
        algo_menu.config(bg="#f5f0e8")
        algo_menu.pack(fill=tk.X, padx=6, pady=(0, 4))

        for label_text, var in [("Min Green (s)", self.node_min_green_var),
                                  ("Max Green (s)", self.node_max_green_var),
                                  ("Service Rate", self.node_service_var)]:
            tk.Label(self.signal_controls_frame, text=label_text, bg="#ded5c4", font=("Arial", 9)).pack(anchor="w", padx=6)
            tk.Entry(self.signal_controls_frame, textvariable=var).pack(fill=tk.X, padx=6, pady=(0, 4))

        tk.Label(self.signal_controls_frame, text="(Min/Max Green apply only to signalized junctions\nwith 2+ incoming roads)",
                 bg="#ded5c4", fg="#665544", font=("Arial", 8), justify=tk.LEFT,
                 wraplength=300).pack(anchor="w", padx=6, pady=(0, 8))
        self.signal_disabled_msg = tk.Label(
            adv,
            text="Signal settings are not used for source/sink junctions.",
            bg="#ded5c4",
            fg="#665544",
            font=("Arial", 9, "italic"),
            justify=tk.LEFT,
            wraplength=300,
        )

        # ── Action buttons ───────────────────────────────────────────
        btn_frame = tk.Frame(self.node_form, bg="#ded5c4")
        btn_frame.pack(fill=tk.X, padx=6, pady=8)
        tk.Button(btn_frame, text="✔  Apply Junction", command=self._apply_node_form,
                  bg="#3a7a3a", fg="white", font=("Arial", 10, "bold"),
                  relief="raised").pack(fill=tk.X, pady=(0, 4))
        tk.Button(btn_frame, text="🗑  Delete Selected", command=self._delete_selected,
                  bg="#9a2a2a", fg="white", font=("Arial", 10, "bold"),
                  relief="raised").pack(fill=tk.X)

    def _build_road_form(self) -> None:
        self.road_form = tk.Frame(self.form, bg="#ded5c4")
        self.road_id_var     = tk.StringVar()
        self.road_from_var   = tk.StringVar()
        self.road_to_var     = tk.StringVar()
        self.road_length_var = tk.StringVar(value="120")
        self.road_speed_var  = tk.StringVar(value="12")
        # Lane type: human-friendly choice; maps to lanes-per-direction count
        self.road_lane_type_var = tk.StringVar(value="2-lane (1+1)")

        p = 6
        bg = "#ded5c4"

        # Road ID (read-only display)
        tk.Label(self.road_form, text="Road ID", bg=bg, font=("Arial", 9, "bold")).pack(anchor="w", padx=p)
        tk.Entry(self.road_form, textvariable=self.road_id_var, state="readonly",
                 readonlybackground="#e8e0d0").pack(fill=tk.X, padx=p, pady=(0, 6))

        # From / To (read-only)
        row_ft = tk.Frame(self.road_form, bg=bg)
        row_ft.pack(fill=tk.X, padx=p, pady=(0, 6))
        for lbl, var in [("From", self.road_from_var), ("To", self.road_to_var)]:
            col = tk.Frame(row_ft, bg=bg)
            col.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
            tk.Label(col, text=lbl, bg=bg, font=("Arial", 9, "bold")).pack(anchor="w")
            tk.Entry(col, textvariable=var, state="readonly",
                     readonlybackground="#e8e0d0", width=8).pack(fill=tk.X)

        # Lane configuration dropdown
        tk.Label(self.road_form, text="Lane Configuration", bg=bg, font=("Arial", 9, "bold")).pack(anchor="w", padx=p)
        LANE_OPTIONS = [
            "2-lane (1+1)",
            "4-lane (2+2)",
            "8-lane (4+4)",
        ]
        lane_menu = tk.OptionMenu(self.road_form, self.road_lane_type_var, *LANE_OPTIONS)
        lane_menu.config(bg="#f5f0e8", anchor="w")
        lane_menu.pack(fill=tk.X, padx=p, pady=(0, 4))

        tk.Label(self.road_form,
                 text="India rule: vehicles keep LEFT.\n"
                      "Each direction gets equal lanes.\n"
                      "Lane directions are set automatically.",
                 bg=bg, fg="#665544", font=("Arial", 8), justify=tk.LEFT,
                 wraplength=310).pack(anchor="w", padx=p, pady=(0, 8))

        # Speed limit
        tk.Label(self.road_form, text="Speed Limit (m/s)", bg=bg, font=("Arial", 9, "bold")).pack(anchor="w", padx=p)
        tk.Entry(self.road_form, textvariable=self.road_speed_var).pack(fill=tk.X, padx=p, pady=(0, 6))

        # Length (read-only, auto-computed from node positions)
        tk.Label(self.road_form, text="Length (m)  — auto from positions", bg=bg, font=("Arial", 8)).pack(anchor="w", padx=p)
        tk.Entry(self.road_form, textvariable=self.road_length_var, state="readonly",
                 readonlybackground="#e8e0d0").pack(fill=tk.X, padx=p, pady=(0, 10))

        road_btn_frame = tk.Frame(self.road_form, bg=bg)
        road_btn_frame.pack(fill=tk.X, padx=p, pady=4)
        tk.Button(road_btn_frame, text="✔  Apply Road", command=self._apply_road_form,
                  bg="#3a7a3a", fg="white", font=("Arial", 10, "bold")).pack(fill=tk.X, pady=(0, 4))
        tk.Button(road_btn_frame, text="🗑  Delete Road", command=self._delete_selected,
                  bg="#9a2a2a", fg="white", font=("Arial", 10, "bold")).pack(fill=tk.X)

    def _on_role_changed(self) -> None:
        """Called when source/sink checkboxes change — show/hide vehicle types tab."""
        is_source = self.node_source_var.get()
        if self._nb is not None:
            try:
                if is_source:
                    self._nb.tab(0, state="normal")
                else:
                    self._nb.tab(0, state="disabled")
                    self._nb.select(1)
            except Exception:
                pass
        self._refresh_signal_controls()
        self._refresh_dest_dropdowns(self.node_id_var.get().strip() or self.selected_id or "")
        self._refresh_source_rate_display()

    def _refresh_source_rate_display(self) -> None:
        total = 0.0
        if self.node_source_var.get():
            for row in self._vtype_rows:
                total += _safe_float(row["flow"].get(), 0.0)
        self.node_source_rate_var.set(f"{total:.3f}")

    def _get_possible_destinations(self, exclude_id: str) -> List[str]:
        """Return sink junction IDs available as destinations for a source."""
        return sorted(
            [
                n["id"]
                for n in self.network["nodes"]
                if n["id"] != exclude_id and n.get("is_sink", False)
            ]
        )

    def _refresh_dest_dropdowns(self, current_node_id: str) -> None:
        """Repopulate destination OptionMenus with nodes reachable from current_node_id."""
        choices = self._get_possible_destinations(current_node_id)
        if not choices:
            choices = [""]
        for row in self._vtype_rows:
            menu = row["dest_om"]["menu"]
            menu.delete(0, "end")
            menu.add_command(label="(none)", command=lambda v=row["dest"]: v.set(""))
            for c in choices:
                menu.add_command(label=c, command=lambda v=row["dest"], val=c: v.set(val))
            if row["dest"].get() not in choices:
                row["dest"].set("")

    def _refresh_signal_controls(self) -> None:
        show_signals = not (self.node_source_var.get() or self.node_sink_var.get())
        if show_signals:
            if not self.signal_controls_frame.winfo_ismapped():
                self.signal_controls_frame.pack(fill=tk.X, padx=0, pady=0)
            if self.signal_disabled_msg.winfo_ismapped():
                self.signal_disabled_msg.pack_forget()
        else:
            if self.signal_controls_frame.winfo_ismapped():
                self.signal_controls_frame.pack_forget()
            if not self.signal_disabled_msg.winfo_ismapped():
                self.signal_disabled_msg.pack(fill=tk.X, padx=6, pady=(8, 8))


    def _bind_canvas(self) -> None:
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

    def _load_if_exists(self) -> None:
        path = Path(self.json_path)
        if path.exists():
            self.network = load_network_definition(self.json_path)

    def _toolbar_action(self, action: str) -> None:
        if action == "save":
            self._save_file()
            return
        if action == "open":
            self._open_file()
            return
        if action == "demo":
            self.network = json.loads(json.dumps(DEFAULT_NETWORK))
            self.selected_kind = None
            self.selected_id = None
            self._show_form(None)
            self.status.set("Loaded demo network")
            self._redraw()
            return
        self.mode = action
        self.draw_start_node = None
        self.status.set(f"Mode: {action}")

    def _on_left_click(self, event) -> None:
        node = self._node_at(event.x, event.y)
        road = None if node else self._road_at(event.x, event.y)

        if self.mode == "junction":
            if node or road:
                self._select_object("node" if node else "road", (node or road)["id"])
                return
            self._add_junction(event.x, event.y)
            return

        if self.mode == "road":
            if node is None:
                return
            if self.draw_start_node is None:
                self.draw_start_node = node["id"]
                self.status.set(f"Road start selected: {node['id']}. Click destination junction.")
                return
            if node["id"] == self.draw_start_node:
                return
            self._add_road(self.draw_start_node, node["id"])
            self.draw_start_node = None
            return

        if node is not None:
            self.dragging_node_id = node["id"]
            self._select_object("node", node["id"])
            return
        if road is not None:
            self._select_object("road", road["id"])
            return

        self.selected_kind = None
        self.selected_id = None
        self._show_form(None)
        self._redraw()

    def _on_drag(self, event) -> None:
        if self.dragging_node_id is None or self.mode != "select":
            return
        node = self._find_node(self.dragging_node_id)
        node["x"] = int(event.x)
        node["y"] = int(event.y)
        self._refresh_lengths_for_node(node["id"])
        self._load_selection_into_form()
        self._redraw()

    def _on_release(self, _event) -> None:
        self.dragging_node_id = None

    def _on_double_click(self, event) -> None:
        node = self._node_at(event.x, event.y)
        if node is not None:
            self._select_object("node", node["id"])
            return
        road = self._road_at(event.x, event.y)
        if road is not None:
            self._select_object("road", road["id"])

    def _on_right_click(self, event) -> None:
        node = self._node_at(event.x, event.y)
        if node is not None:
            self._select_object("node", node["id"])
            return
        road = self._road_at(event.x, event.y)
        if road is not None:
            self._select_object("road", road["id"])

    def _add_junction(self, x: int, y: int) -> None:
        node = {
            "id": self._next_id("J"),
            "x": int(x),
            "y": int(y),
            "is_source": False,
            "is_sink": False,
            "source_rate": 0.25,
            "source_mode": "poisson",
            "destinations": [],
            "destination_weights": {},
            "signal_algorithm": "wfq_lane",
            "min_green": 4,
            "max_green": 12,
            "service_rate": 1,
            "junction_width": 60,
            "junction_height": 60,
        }
        self.network["nodes"].append(node)
        self._select_object("node", node["id"])
        self.status.set(f"Added junction {node['id']}")

    def _add_road(self, from_id: str, to_id: str) -> None:
        start = self._find_node(from_id)
        end = self._find_node(to_id)
        corridor_number = self._next_corridor_number()
        corridor_id = f"C{corridor_number}"
        lane_count = 1
        length = int(round(math.hypot(end["x"] - start["x"], end["y"] - start["y"])))
        road_a = {
            "id": f"R{corridor_number}A",
            "from": from_id,
            "to": to_id,
            "length": length,
            "speed_limit": 12,
            "lanes": lane_count,
            "lane_directions": [["*"] for _ in range(lane_count)],
            "lane_flow_weights": [1.0 for _ in range(lane_count)],
            "corridor_id": corridor_id,
        }
        road_b = {
            "id": f"R{corridor_number}B",
            "from": to_id,
            "to": from_id,
            "length": length,
            "speed_limit": 12,
            "lanes": lane_count,
            "lane_directions": [["*"] for _ in range(lane_count)],
            "lane_flow_weights": [1.0 for _ in range(lane_count)],
            "corridor_id": corridor_id,
        }
        self.network["roads"].extend([road_a, road_b])
        self._select_object("road", road_a["id"])
        self.status.set(f"Added bidirectional corridor {corridor_id}")

    def _select_object(self, kind: str, object_id: str) -> None:
        # Auto-save current node form before switching away, so data is never lost
        if self.selected_kind == "node" and self.selected_id is not None:
            try:
                self._apply_node_form()
            except Exception:
                pass
        self.selected_kind = kind
        self.selected_id = object_id
        self._load_selection_into_form()
        self._redraw()

    def _load_selection_into_form(self) -> None:
        if self.selected_kind == "node" and self.selected_id is not None:
            node = self._find_node(self.selected_id)
            self.object_name.set(f"Junction {node['id']}")
            self.node_id_var.set(node["id"])
            self.node_source_var.set(bool(node.get("is_source")))
            self.node_sink_var.set(bool(node.get("is_sink")))
            self.node_signal_algo_var.set(node.get("signal_algorithm", "wfq_lane"))
            self.node_min_green_var.set(str(node.get("min_green", 4)))
            self.node_max_green_var.set(str(node.get("max_green", 12)))
            self.node_service_var.set(str(node.get("service_rate", 1)))
            self.node_size_var.set(str(node.get("junction_width", 60)))

            # Refresh destination dropdowns for this node
            self._refresh_dest_dropdowns(node["id"])

            # Populate vehicle type rows
            vtypes = node.get("vehicle_types", [])
            for vt_idx, row_vars in enumerate(self._vtype_rows):
                if vt_idx < len(vtypes):
                    vt = vtypes[vt_idx]
                    row_vars["dest"].set(vt.get("destination", ""))
                    row_vars["flow"].set(str(vt.get("flow_rate", 0.0)))
                    row_vars["weight"].set(str(vt.get("weight", vt_idx + 1)))
                else:
                    row_vars["dest"].set("")
                    row_vars["flow"].set("0.0")
                    row_vars["weight"].set(str(vt_idx + 1))

            self._refresh_source_rate_display()
            self._refresh_signal_controls()

            # Show/hide vehicle types tab based on source role
            if self._nb is not None:
                try:
                    state = "normal" if node.get("is_source") else "disabled"
                    self._nb.tab(0, state=state)
                    if not node.get("is_source"):
                        self._nb.select(1)
                except Exception:
                    pass

            self._show_form("node")
            return

        if self.selected_kind == "road" and self.selected_id is not None:
            road = self._find_road(self.selected_id)
            # Show the corridor partner label if this is one side of a corridor
            corridor_id = road.get("corridor_id", "")
            display_id = f"{road['id']}  [{corridor_id}]" if corridor_id else road["id"]
            self.object_name.set(f"Road  {display_id}")
            self.road_id_var.set(road["id"])
            self.road_from_var.set(road["from"])
            self.road_to_var.set(road["to"])
            self.road_length_var.set(str(road.get("length", 120)))
            self.road_speed_var.set(str(road.get("speed_limit", 12)))
            # Map lanes-per-direction to human label
            lanes = road.get("lanes", 2)
            mapping = {1: "2-lane (1+1)", 2: "4-lane (2+2)", 4: "8-lane (4+4)"}
            self.road_lane_type_var.set(mapping.get(lanes, "2-lane (1+1)"))
            self._show_form("road")
            return

        self.object_name.set("No selection")
        self._show_form(None)

    def _show_form(self, form_name: Optional[str]) -> None:
        self.node_form.pack_forget()
        self.road_form.pack_forget()
        if form_name == "node":
            self.node_form.pack(fill=tk.BOTH, expand=True)
        elif form_name == "road":
            self.road_form.pack(fill=tk.BOTH, expand=True)

    def _apply_node_form(self) -> None:
        if self.selected_kind != "node" or self.selected_id is None:
            return
        node = self._find_node(self.selected_id)
        new_id = self.node_id_var.get().strip() or node["id"]
        old_id = node["id"]

        # Update roads that reference this node if ID changed
        if new_id != old_id:
            for road in self.network["roads"]:
                if road["from"] == old_id:
                    road["from"] = new_id
                if road["to"] == old_id:
                    road["to"] = new_id
            for other_node in self.network["nodes"]:
                if other_node["id"] == old_id:
                    continue
                other_node["destinations"] = [
                    new_id if d == old_id else d
                    for d in other_node.get("destinations", [])
                ]
                if old_id in other_node.get("destination_weights", {}):
                    w = other_node["destination_weights"].pop(old_id)
                    other_node["destination_weights"][new_id] = w
                vtypes = other_node.get("vehicle_types", [])
                for vt in vtypes:
                    if vt.get("destination") == old_id:
                        vt["destination"] = new_id

        node["id"] = new_id
        is_source = bool(self.node_source_var.get())
        is_sink = bool(self.node_sink_var.get())
        node["is_source"] = is_source
        node["is_sink"] = is_sink
        # Both source and sink allowed (pass-through node) — no forced reset

        node["signal_algorithm"] = self.node_signal_algo_var.get().strip() or "wfq_lane"
        node["min_green"] = _safe_float(self.node_min_green_var.get(), 4.0)
        node["max_green"] = _safe_float(self.node_max_green_var.get(), 12.0)
        node["service_rate"] = max(1, _safe_int(self.node_service_var.get(), 1))

        size = max(40, _safe_int(self.node_size_var.get(), 60))
        node["junction_width"] = size
        node["junction_height"] = size

        DEST_COLORS = ["#e53935", "#43a047", "#1e88e5", "#fb8c00", "#8e24aa"]
        vtypes = []
        destinations = []
        destination_weights = {}
        total_rate = 0.0
        allowed_destinations = set(self._get_possible_destinations(new_id))
        for vt_idx, row_vars in enumerate(self._vtype_rows):
            dest = row_vars["dest"].get().strip()
            flow = _safe_float(row_vars["flow"].get(), 0.0)
            wt   = max(1, min(5, _safe_int(row_vars["weight"].get(), vt_idx + 1)))
            if is_source and dest in allowed_destinations and flow > 0:
                vtypes.append({
                    "type_id": vt_idx + 1,
                    "destination": dest,
                    "flow_rate": flow,
                    "weight": wt,
                    "color": DEST_COLORS[vt_idx],
                })
                total_rate += flow
                if dest not in destinations:
                    destinations.append(dest)
                destination_weights[dest] = destination_weights.get(dest, 0.0) + flow

        node["vehicle_types"] = vtypes
        node["destinations"] = destinations
        node["destination_weights"] = destination_weights
        node["source_rate"] = total_rate if is_source else 0.0
        self.node_source_rate_var.set(f"{total_rate:.3f}")

        self.selected_id = node["id"]
        self.status.set(f"Updated junction {node['id']}")
        self._redraw()

    def _apply_road_form(self) -> None:
        if self.selected_kind != "road" or self.selected_id is None:
            return
        road = self._find_road(self.selected_id)
        speed = max(1.0, _safe_float(self.road_speed_var.get(), 12.0))
        label = self.road_lane_type_var.get()
        lanes_map = {
            "2-lane (1+1)": 1,
            "4-lane (2+2)": 2,
            "8-lane (4+4)": 4,
        }
        lanes_per_dir = lanes_map.get(label, 1)

        # Apply to this road
        road["speed_limit"] = speed
        road["lanes"] = lanes_per_dir
        road["lane_directions"] = [["*"] for _ in range(lanes_per_dir)]
        road["lane_flow_weights"] = [1.0] * lanes_per_dir

        # Mirror same lanes/speed to the corridor partner (opposite direction)
        corridor_id = road.get("corridor_id")
        if corridor_id:
            for sibling in self.network["roads"]:
                if sibling.get("corridor_id") == corridor_id and sibling["id"] != road["id"]:
                    sibling["speed_limit"] = speed
                    sibling["lanes"] = lanes_per_dir
                    sibling["lane_directions"] = [["*"] for _ in range(lanes_per_dir)]
                    sibling["lane_flow_weights"] = [1.0] * lanes_per_dir

        self.selected_id = road["id"]
        self.status.set(f"Updated road {road['id']}  ({lanes_per_dir} lanes/dir, {speed} m/s)")
        self._redraw()

    def _delete_selected(self) -> None:
        if self.selected_kind == "node" and self.selected_id is not None:
            node_id = self.selected_id
            self.network["nodes"] = [node for node in self.network["nodes"] if node["id"] != node_id]
            self.network["roads"] = [road for road in self.network["roads"] if road["from"] != node_id and road["to"] != node_id]
            for node in self.network["nodes"]:
                node["destinations"] = [dest for dest in node.get("destinations", []) if dest != node_id]
                node["destination_weights"] = {
                    key: value for key, value in node.get("destination_weights", {}).items() if key != node_id
                }
            self.status.set(f"Deleted junction {node_id}")
        elif self.selected_kind == "road" and self.selected_id is not None:
            road_id = self.selected_id
            self.network["roads"] = [road for road in self.network["roads"] if road["id"] != road_id]
            for road in self.network["roads"]:
                road["lane_directions"] = [
                    [target for target in lane if target != road_id] or ["*"]
                    for lane in road.get("lane_directions", [["*"]])
                ]
            self.status.set(f"Deleted road {road_id}")
        self.selected_kind = None
        self.selected_id = None
        self._show_form(None)
        self._redraw()

    def _open_file(self) -> None:
        if filedialog is None:
            return
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")], initialfile=self.json_path)
        if not path:
            return
        self.network = load_network_definition(path)
        self.json_path = path
        self.selected_kind = None
        self.selected_id = None
        self._show_form(None)
        self.status.set(f"Opened {Path(path).name}")
        self._redraw()

    def _save_file(self) -> None:
        if filedialog is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], initialfile=self.json_path)
        if not path:
            return
        save_network_definition(self.network, path)
        self.json_path = path
        if messagebox is not None:
            messagebox.showinfo("Traffic NetEdit", f"Saved network to {path}")

    def _refresh_lengths_for_node(self, node_id: str) -> None:
        for road in self.network["roads"]:
            if road["from"] == node_id or road["to"] == node_id:
                start = self._find_node(road["from"])
                end = self._find_node(road["to"])
                road["length"] = int(round(math.hypot(end["x"] - start["x"], end["y"] - start["y"])))

    def _node_at(self, x: float, y: float) -> Optional[dict]:
        for node in self.network["nodes"]:
            width = node.get("junction_width", 60)
            height = node.get("junction_height", 60)
            if abs(node["x"] - x) <= width / 2 and abs(node["y"] - y) <= height / 2:
                return node
        return None

    def _road_at(self, x: float, y: float) -> Optional[dict]:
        best_road = None
        best_distance = 18.0
        for road in self.network["roads"]:
            start = self._find_node(road["from"])
            end = self._find_node(road["to"])
            distance = _distance_to_segment((x, y), (start["x"], start["y"]), (end["x"], end["y"]))
            if distance < best_distance:
                best_road = road
                best_distance = distance
        return best_road

    def _find_node(self, node_id: str) -> Dict:
        for node in self.network["nodes"]:
            if node["id"] == node_id:
                return node
        raise KeyError(node_id)

    def _find_road(self, road_id: str) -> Dict:
        for road in self.network["roads"]:
            if road["id"] == road_id:
                return road
        raise KeyError(road_id)

    def _next_id(self, prefix: str) -> str:
        existing = {node["id"] for node in self.network["nodes"]} | {road["id"] for road in self.network["roads"]}
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        return f"{prefix}{index}"

    def _redraw(self) -> None:
        self.canvas.delete("all")
        self._draw_grid()
        drawn_corridors = set()
        for road in self.network["roads"]:
            corridor_id = road.get("corridor_id")
            if corridor_id and corridor_id in drawn_corridors:
                continue
            if corridor_id:
                siblings = [candidate for candidate in self.network["roads"] if candidate.get("corridor_id") == corridor_id]
                if len(siblings) == 2:
                    self._draw_corridor(siblings[0], siblings[1])
                    drawn_corridors.add(corridor_id)
                    continue
            self._draw_road(road)
        for node in self.network["nodes"]:
            self._draw_node(node)
        self._draw_legend()

    def _draw_legend(self) -> None:
        """Draw a compact role legend in the top-right corner of the canvas."""
        cw = self.canvas.winfo_width() or 820
        lx = cw - 10
        ly = 10
        items = [
            ("#2e6b2e", "SRC – Source"),
            ("#7a2a2a", "SNK – Sink"),
            ("#5a7a3a", "SRC+SNK"),
            ("#40566b", "Junction"),
        ]
        box_w, box_h = 130, 14
        pad = 6
        total_h = len(items) * (box_h + pad) + pad
        self.canvas.create_rectangle(lx - box_w - pad*2, ly, lx, ly + total_h,
                                     fill="#f0e8d8", outline="#9a8a70", width=1)
        for i, (color, label) in enumerate(items):
            iy = ly + pad + i * (box_h + pad)
            self.canvas.create_rectangle(lx - box_w - pad, iy, lx - box_w - pad + 14, iy + box_h,
                                         fill=color, outline="#333", width=1)
            self.canvas.create_text(lx - box_w - pad + 18, iy + box_h // 2,
                                    text=label, anchor="w", fill="#1a1a1a", font=("Arial", 8))

    def _draw_corridor(self, road_a: dict, road_b: dict) -> None:
        start = self._find_node(road_a["from"])
        end = self._find_node(road_a["to"])
        lanes_total = int(road_a.get("lanes", 2)) + int(road_b.get("lanes", 2))
        width = 12 + lanes_total * 6
        selected = self.selected_kind == "road" and self.selected_id in {road_a["id"], road_b["id"]}
        color = "#b77934" if selected else "#8c8474"
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill="#5d5348", width=width + 4, capstyle=tk.BUTT)
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill=color, width=width, capstyle=tk.BUTT)
        for lane_index in range(1, lanes_total):
            offset = lane_index - lanes_total / 2
            sx, sy = _offset_point((start["x"], start["y"]), (end["x"], end["y"]), offset, 7.0)
            ex, ey = _offset_point((end["x"], end["y"]), (start["x"], start["y"]), -offset, 7.0)
            line_color = "#f4d35e" if lane_index == lanes_total // 2 else "#d9d4c9"
            dash = () if lane_index == lanes_total // 2 else (8, 6)
            self.canvas.create_line(sx, sy, ex, ey, fill=line_color, dash=dash, width=1)
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill="#2e2a26", arrow=tk.LAST, arrowshape=(14, 16, 6), width=1)
        self.canvas.create_line(end["x"], end["y"], start["x"], start["y"], fill="#2e2a26", arrow=tk.LAST, arrowshape=(14, 16, 6), width=1)
        mx = (start["x"] + end["x"]) / 2
        my = (start["y"] + end["y"]) / 2
        self.canvas.create_text(mx, my - 14, text=f"{road_a.get('corridor_id', road_a['id'])}  4L", fill="#2a2520", font=("Arial", 9, "bold"))

    def _next_corridor_number(self) -> int:
        numbers = []
        for road in self.network["roads"]:
            corridor_id = road.get("corridor_id", "")
            if corridor_id.startswith("C"):
                try:
                    numbers.append(int(corridor_id[1:]))
                except ValueError:
                    continue
        return max(numbers, default=0) + 1

    def _draw_grid(self) -> None:
        for x in range(0, 1400, 40):
            self.canvas.create_line(x, 0, x, 900, fill="#eee5d7")
        for y in range(0, 1000, 40):
            self.canvas.create_line(0, y, 1400, y, fill="#eee5d7")

    def _draw_road(self, road: dict) -> None:
        start = self._find_node(road["from"])
        end = self._find_node(road["to"])
        lanes = max(1, int(road.get("lanes", 1)))
        width = 10 + lanes * 8
        color = "#b77934" if self.selected_kind == "road" and self.selected_id == road["id"] else "#8c8474"
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill="#5d5348", width=width + 4, capstyle=tk.BUTT)
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill=color, width=width, capstyle=tk.BUTT)
        for lane_index in range(1, lanes):
            offset = lane_index - lanes / 2
            sx, sy = _offset_point((start["x"], start["y"]), (end["x"], end["y"]), offset, 8.0)
            ex, ey = _offset_point((end["x"], end["y"]), (start["x"], start["y"]), -offset, 8.0)
            self.canvas.create_line(sx, sy, ex, ey, fill="#d9d4c9", dash=(8, 6), width=1)
        self.canvas.create_line(start["x"], start["y"], end["x"], end["y"], fill="#2e2a26", arrow=tk.LAST, arrowshape=(14, 16, 6), width=1)
        mx = (start["x"] + end["x"]) / 2
        my = (start["y"] + end["y"]) / 2
        self.canvas.create_text(mx, my - 14, text=f"{road['id']}  {lanes}L", fill="#2a2520", font=("Arial", 9, "bold"))

    def _draw_node(self, node: dict) -> None:
        width = node.get("junction_width", 80)*0.55
        height = node.get("junction_height", 80)*0.55
        x, y = node["x"], node["y"]
        x1, y1 = x - width / 2, y - height / 2
        x2, y2 = x + width / 2, y + height / 2
        selected = self.selected_kind == "node" and self.selected_id == node["id"]

        # Base fill by role
        is_source = node.get("is_source", False)
        is_sink = node.get("is_sink", False)
        if is_source and is_sink:
            fill = "#5a7a3a" if not selected else "#7aaa4a"
        elif is_source:
            fill = "#2e6b2e" if not selected else "#3d8f3d"
        elif is_sink:
            fill = "#7a2a2a" if not selected else "#a03030"
        else:
            fill = "#40566b" if not selected else "#5a6c7d"

        # Outer border (SUMO-style thick dark border)
        self.canvas.create_rectangle(x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                                    fill="#1c2a36", outline="", width=0)
        # Main junction box
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                    fill=fill, outline="#0d1820", width=2)

        # Interior crosshatch (SUMO style) — only for intermediate junctions
        if not is_source and not is_sink:
            hatch_color = "#34495a"
            spacing = 8
            # Diagonal lines /
            for offset in range(-int(width + height), int(width + height), spacing):
                lx1 = x1
                ly1 = y1 + offset
                lx2 = x1 + offset
                ly2 = y1
                # Clip to rectangle bounds
                pts = _clip_line_to_rect(lx1, ly1, lx2, ly2, x1, y1, x2, y2)
                if pts:
                    self.canvas.create_line(*pts, fill=hatch_color, width=1)

        # Signal heads: small circles on each edge where roads connect
        incoming_roads = [r for r in self.network["roads"] if r["to"] == node["id"]]
        num_incoming = len(incoming_roads)
        if num_incoming >= 2 and not is_source and not is_sink:
            # Place a signal head on the inner edge of each incoming road arm
            for road in incoming_roads:
                from_node = self._find_node(road["from"])
                # Direction vector from junction toward from_node
                dx = from_node["x"] - x
                dy = from_node["y"] - y
                dist = max(1.0, (dx**2 + dy**2) ** 0.5)
                # Place signal at junction edge
                edge_x = x + (dx / dist) * (width / 2 - 4)
                edge_y = y + (dy / dist) * (height / 2 - 4)
                # Draw a small 3-light signal post (green/amber/red stacked)
                for si, sc in enumerate(["#e74c3c", "#f39c12", "#2ecc71"]):
                    self.canvas.create_oval(
                        edge_x - 3, edge_y - 3 + si * 7,
                        edge_x + 3, edge_y + 3 + si * 7,
                        fill=sc, outline="#111", width=1
                    )

        # Junction ID
        self.canvas.create_text(x, y, text=node["id"], fill="white",
                                font=("Arial", 10, "bold"))

        # No role badges below node — roles shown in corner legend
    
    def run(self) -> None:
        self.root.mainloop()


def _safe_float(text: str, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _safe_int(text: str, default: int) -> int:
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _csv_list(text: str) -> List[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _weights_to_text(weights: Dict[str, float]) -> str:
    return ", ".join(f"{key}:{value}" for key, value in weights.items())


def _text_to_weights(text: str) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for chunk in text.split(","):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        key = key.strip()
        if key:
            result[key] = _safe_float(value.strip(), 1.0)
    return result


def _lane_directions_to_text(lane_directions: List[List[str]]) -> str:
    parts = []
    for index, lane in enumerate(lane_directions, start=1):
        parts.append(f"lane{index}={'|'.join(lane)}")
    return " ; ".join(parts)


def _text_to_lane_directions(text: str, lane_count: int) -> List[List[str]]:
    mapping: Dict[int, List[str]] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, payload = chunk.split("=", 1)
        name = name.strip().lower()
        if not name.startswith("lane"):
            continue
        lane_index = _safe_int(name[4:], 1) - 1
        mapping[lane_index] = [item.strip() for item in payload.split("|") if item.strip()] or ["*"]
    result: List[List[str]] = []
    for index in range(lane_count):
        result.append(mapping.get(index, ["*"]))
    return result


def _text_to_float_list(text: str, lane_count: int) -> List[float]:
    values = [_safe_float(chunk.strip(), 1.0) for chunk in text.split(",") if chunk.strip()]
    while len(values) < lane_count:
        values.append(1.0)
    return values[:lane_count]


def _offset_point(start: tuple, end: tuple, lane_offset: float, spacing: float) -> tuple:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    return start[0] + nx * lane_offset * spacing, start[1] + ny * lane_offset * spacing


def _distance_to_segment(point: tuple, start: tuple, end: tuple) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / float(dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

def _clip_line_to_rect(lx1, ly1, lx2, ly2, rx1, ry1, rx2, ry2):
    """Cohen-Sutherland clip: return clipped (x1,y1,x2,y2) or None."""
    def code(x, y):
        c = 0
        if x < rx1: c |= 1
        elif x > rx2: c |= 2
        if y < ry1: c |= 4
        elif y > ry2: c |= 8
        return c
    c1, c2 = code(lx1, ly1), code(lx2, ly2)
    while True:
        if not (c1 | c2): return (lx1, ly1, lx2, ly2)
        if c1 & c2: return None
        c = c1 if c1 else c2
        if c & 1:   x = rx1; y = ly1 + (ly2-ly1)*(rx1-lx1)/(lx2-lx1+1e-9)
        elif c & 2: x = rx2; y = ly1 + (ly2-ly1)*(rx2-lx1)/(lx2-lx1+1e-9)
        elif c & 4: y = ry1; x = lx1 + (lx2-lx1)*(ry1-ly1)/(ly2-ly1+1e-9)
        else:       y = ry2; x = lx1 + (lx2-lx1)*(ry2-ly1)/(ly2-ly1+1e-9)
        if c == c1: lx1,ly1,c1 = x,y,code(x,y)
        else:       lx2,ly2,c2 = x,y,code(x,y)
