import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import numpy as np
import os
import csv
import urllib.request
import urllib.parse
from skyfield.api import load, wgs84
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# --- CONFIGURATION ---
DEFAULT_TZ_NAME = "Europe/Berlin"
GCAT_URL = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
GCAT_FILENAME = "satcat.tsv"

CELESTRAK_GROUPS = {
    "starlink": {"name": "Starlink", "file": "starlink_bulk.txt", "default": True},
    "stations": {"name": "Space Stations (ISS, Tiangong)", "file": "stations_bulk.txt", "default": False},
    "visual": {"name": "Brightest Satellites (Visual Show)", "file": "visual_bulk.txt", "default": False},
    "iridium-33-debris": {"name": "Iridium 33 Debris (Large Parts)", "file": "iridium_33_debris_bulk.txt",
                          "default": False},
    "weather": {"name": "Weather Satellites", "file": "weather_bulk.txt", "default": False},
    "gps": {"name": "GPS Satellites", "file": "gps_bulk.txt", "default": False},
    "resource": {"name": "Earth Resources (Landsat, Sentinel)", "file": "resource_bulk.txt", "default": False},
    "active": {"name": "All Active Satellites (Very Large!)", "file": "active_bulk.txt", "default": False}
}


class TransitApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Solar Transit Finder & Field Visualizer")
        self.root.geometry("1300x880")

        self.sort_ascending = {}
        self.loaded_satellites = {}
        self.current_results = []
        self.selected_transit_data = None
        self.path_points = []

        # Canvas interactive coordinate states
        self.canvas_center_x = 180
        self.canvas_center_y = 180
        self.fov_center_x = 180
        self.fov_center_y = 180
        self.sun_radius_px = 80.0  # Represents ~0.266 degrees radius
        self.deg_per_px = 0.266 / self.sun_radius_px

        # Ephemeris placeholders
        self.sun_base_ra = 0.0
        self.sun_base_dec = 0.0

        self.setup_styles()
        self.setup_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        self.bg_color = "#f8fafc"
        self.card_bg = "#ffffff"
        self.primary_color = "#4f46e5"
        self.primary_hover = "#4338ca"
        self.secondary_color = "#0f172a"
        self.border_color = "#e2e8f0"
        self.accent_green = "#16a34a"

        self.root.configure(bg=self.bg_color)

        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TLabelframe", background=self.card_bg, bordercolor=self.border_color, borderwidth=1,
                        relief="solid")
        style.configure("Card.TLabelframe.Label", background=self.card_bg, foreground=self.secondary_color,
                        font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background=self.bg_color, foreground="#334155", font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=self.card_bg, foreground="#334155", font=("Segoe UI", 9))
        style.configure("Card.TCheckbutton", background=self.card_bg, foreground="#334155", font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=self.border_color,
                        lightcolor=self.border_color, darkcolor=self.border_color)

        style.configure("Primary.TButton", background=self.primary_color, foreground="#ffffff", borderwidth=0,
                        font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.map("Primary.TButton", background=[("active", self.primary_hover), ("disabled", "#94a3b8")])
        style.configure("Secondary.TButton", background="#ffffff", foreground=self.primary_color,
                        bordercolor=self.primary_color, borderwidth=1, font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.map("Secondary.TButton", background=[("active", "#f1f5f9")])

        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26, background="#ffffff", fieldbackground="#ffffff",
                        gridcolor=self.border_color)
        style.configure("Treeview.Heading", background=self.secondary_color, foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"), padding=5)
        style.map("Treeview.Heading", background=[("active", "#1e293b")])
        style.map("Treeview", background=[("selected", "#e0e7ff")], foreground=[("selected", "#1e1b4b")])

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- SETTINGS PARAMETERS ---
        settings_frame = ttk.LabelFrame(main_frame, text=" Observation & Camera Parameters ", padding="15",
                                        style="Card.TLabelframe")
        settings_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(settings_frame, text="Latitude (Lat):", style="Card.TLabel").grid(row=0, column=0, sticky=tk.W,
                                                                                    pady=4)
        self.lat_var = tk.DoubleVar(value=49.8728)
        ttk.Entry(settings_frame, textvariable=self.lat_var, width=12, takefocus=False).grid(row=0, column=1, padx=5,
                                                                                             pady=4)

        ttk.Label(settings_frame, text="Longitude (Lon):", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W,
                                                                                     pady=4)
        self.lon_var = tk.DoubleVar(value=8.6512)
        ttk.Entry(settings_frame, textvariable=self.lon_var, width=12, takefocus=False).grid(row=1, column=1, padx=5,
                                                                                             pady=4)

        self.tz_var = tk.StringVar(value=DEFAULT_TZ_NAME)
        ttk.Label(settings_frame, text="Timezone (IANA):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W,
                                                                                     pady=4)
        ttk.Entry(settings_frame, textvariable=self.tz_var, width=12, takefocus=False).grid(row=2, column=1, padx=5,
                                                                                            pady=4)

        try:
            tz = ZoneInfo(DEFAULT_TZ_NAME)
        except Exception:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        start_default = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end_default = now.replace(hour=12, minute=0, second=0, microsecond=0)

        ttk.Label(settings_frame, text="Start Time (YYYY-MM-DD HH:MM):", style="Card.TLabel").grid(row=0, column=2,
                                                                                                   sticky=tk.W,
                                                                                                   padx=(25, 0), pady=4)
        self.start_var = tk.StringVar(value=start_default.strftime('%Y-%m-%d %H:%M'))
        self.start_entry = ttk.Entry(settings_frame, textvariable=self.start_var, width=20, takefocus=True)
        self.start_entry.grid(row=0, column=3, padx=5, pady=4)

        ttk.Label(settings_frame, text="End Time (YYYY-MM-DD HH:MM):", style="Card.TLabel").grid(row=1, column=2,
                                                                                                 sticky=tk.W,
                                                                                                 padx=(25, 0), pady=4)
        self.end_var = tk.StringVar(value=end_default.strftime('%Y-%m-%d %H:%M'))
        self.end_entry = ttk.Entry(settings_frame, textvariable=self.end_var, width=20, takefocus=True)
        self.end_entry.grid(row=1, column=3, padx=5, pady=4)

        self.configure_datetime_entry(self.start_entry)
        self.configure_datetime_entry(self.end_entry)

        ttk.Label(settings_frame, text="Focal Length (mm):", style="Card.TLabel").grid(row=0, column=4, sticky=tk.W,
                                                                                       padx=(25, 0), pady=4)
        self.focal_var = tk.DoubleVar(value=1000.0)
        ttk.Entry(settings_frame, textvariable=self.focal_var, width=10, takefocus=False).grid(row=0, column=5, padx=5,
                                                                                               pady=4)

        ttk.Label(settings_frame, text="Pixel Size (µm):", style="Card.TLabel").grid(row=1, column=4, sticky=tk.W,
                                                                                     padx=(25, 0), pady=4)
        self.pixel_var = tk.DoubleVar(value=3.76)
        ttk.Entry(settings_frame, textvariable=self.pixel_var, width=10, takefocus=False).grid(row=1, column=5, padx=5,
                                                                                               pady=4)

        ttk.Label(settings_frame, text="Default HBR (m):", style="Card.TLabel").grid(row=2, column=4, sticky=tk.W,
                                                                                     padx=(25, 0), pady=4)
        self.hbr_var = tk.DoubleVar(value=5.0)
        ttk.Entry(settings_frame, textvariable=self.hbr_var, width=10, takefocus=False).grid(row=2, column=5, padx=5,
                                                                                             pady=4)

        # --- CATALOGUE TRACKING BOXES ---
        celestrak_frame = ttk.LabelFrame(main_frame, text=" CelesTrak Catalogues & Specific Targets ", padding="12",
                                         style="Card.TLabelframe")
        celestrak_frame.pack(fill=tk.X, pady=(0, 12))

        self.check_vars = {}
        row, col = 0, 0
        for key, info in CELESTRAK_GROUPS.items():
            var = tk.BooleanVar(value=info["default"])
            self.check_vars[key] = var
            ttk.Checkbutton(celestrak_frame, text=info["name"], variable=var, style="Card.TCheckbutton",
                            takefocus=False).grid(row=row, column=col, padx=10, pady=4, sticky=tk.W)
            col += 1
            if col > 3: col, row = 0, row + 1

        row += 1
        ttk.Label(celestrak_frame, text="Custom Target(s) (NORAD ID or Name, comma-separated):",
                  style="Card.TLabel").grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(10, 2))
        self.custom_target_var = tk.StringVar(value="")
        self.custom_target_entry = ttk.Entry(celestrak_frame, textvariable=self.custom_target_var, width=40,
                                             takefocus=True)
        self.custom_target_entry.grid(row=row, column=2, columnspan=2, sticky=tk.W, padx=5, pady=(10, 2))

        # --- CONTROLS AREA ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.calc_btn = ttk.Button(btn_frame, text="Calculate Transits", command=self.start_calculation,
                                   style="Primary.TButton", takefocus=False)
        self.calc_btn.pack(side=tk.LEFT)

        self.status_lbl = ttk.Label(btn_frame, text="Ready.", foreground=self.primary_color,
                                    font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(side=tk.LEFT, padx=20)

        # Export Buttons
        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_to_csv,
                                     style="Secondary.TButton", takefocus=False)
        self.export_btn.pack(side=tk.RIGHT)

        self.export_sch_btn = ttk.Button(btn_frame, text="Export Schematic", command=self.export_schematic,
                                         style="Secondary.TButton", takefocus=False)
        self.export_sch_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # --- DATA & VISUALIZATION SPLIT SCREEN CONTAINER ---
        split_frame = ttk.Frame(main_frame)
        split_frame.pack(fill=tk.BOTH, expand=True)

        # Left Column: Table
        table_container = ttk.Frame(split_frame)
        table_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.columns_dict = {
            "name": "Name", "norad": "NORAD ID", "start": "Transit Start (Local)",
            "end": "Transit End (Local)", "duration": "Duration (s)",
            "alt": "Altitude (°)", "hbr": "HBR (m)", "pixels": "Size (Pixels)"
        }
        columns = tuple(self.columns_dict.keys())
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", height=12, takefocus=False)

        for col_id, col_name in self.columns_dict.items():
            self.tree.heading(col_id, text=col_name, command=lambda c=col_id: self.sort_column(c))
            self.sort_ascending[col_id] = True

        self.tree.column("name", width=150)
        self.tree.column("norad", width=70, anchor=tk.CENTER)
        self.tree.column("start", width=150, anchor=tk.CENTER)
        self.tree.column("end", width=150, anchor=tk.CENTER)
        self.tree.column("duration", width=75, anchor=tk.CENTER)
        self.tree.column("alt", width=75, anchor=tk.CENTER)
        self.tree.column("hbr", width=65, anchor=tk.CENTER)
        self.tree.column("pixels", width=85, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_table_row_selected)

        # Right Column: Visualizer Graphical Card
        vis_frame = ttk.LabelFrame(split_frame, text=" Solar Field View Schematic ", padding="10",
                                   style="Card.TLabelframe")
        vis_frame.pack(side=tk.RIGHT, fill=tk.BOTH)

        self.canvas = tk.Canvas(vis_frame, width=360, height=360, bg="#0f172a", highlightthickness=0)
        self.canvas.pack(pady=5)

        # Interactivity hooks for moving the frame
        self.canvas.bind("<Button-1>", self.on_canvas_interaction)
        self.canvas.bind("<B1-Motion>", self.on_canvas_interaction)

        # Coordinate Data Panel Output Elements
        coord_panel = ttk.Frame(vis_frame, style="TFrame")
        coord_panel.pack(fill=tk.X, expand=True, pady=5)

        self.sun_coord_lbl = ttk.Label(coord_panel, text="Sun Center RA/DEC: N/A", font=("Consolas", 9),
                                       background=self.card_bg)
        self.sun_coord_lbl.pack(anchor=tk.W, pady=2, padx=5)

        self.fov_coord_lbl = ttk.Label(coord_panel, text="FOV Center RA/DEC: N/A", font=("Consolas", 9, "bold"),
                                       foreground=self.primary_color, background=self.card_bg)
        self.fov_coord_lbl.pack(anchor=tk.W, pady=2, padx=5)

        self.fov_sz_lbl = ttk.Label(coord_panel, text="Sensor Frame Dimension: N/A", font=("Segoe UI", 8, "italic"),
                                    background=self.card_bg)
        self.fov_sz_lbl.pack(anchor=tk.W, pady=2, padx=5)

        self.draw_empty_canvas()

    def draw_empty_canvas(self):
        self.canvas.delete("all")
        # Draw target radial rings
        self.canvas.create_oval(self.canvas_center_x - self.sun_radius_px, self.canvas_center_y - self.sun_radius_px,
                                self.canvas_center_x + self.sun_radius_px, self.canvas_center_y + self.sun_radius_px,
                                outline="#eab308", width=2, dash=(4, 2))
        self.canvas.create_text(self.canvas_center_x, self.canvas_center_y, text="Solar Disk", fill="#eab308",
                                font=("Segoe UI", 9, "italic"))
        self.canvas.create_text(180, 340, text="[Select a transit row to plot flight path]", fill="#94a3b8",
                                font=("Segoe UI", 8))
        self.draw_fov_box()

    def draw_fov_box(self):
        self.canvas.delete("fov_element")

        focal_len = max(10.0, self.focal_var.get())
        pixel_um = max(0.1, self.pixel_var.get())

        # Simulating standard frame dimension reference of 2000x2000 matrix layout
        fov_rad = (2000.0 * pixel_um * 1e-3) / focal_len
        fov_deg = np.degrees(fov_rad)

        # Defensive sizing protection rules to keep elements from breaking bounding coordinates
        box_px = fov_deg / self.deg_per_px
        box_px = max(12.0, min(box_px, 600.0))

        half_w = box_px / 2.0
        x0, y0 = self.fov_center_x - half_w, self.fov_center_y - half_w
        x1, y1 = self.fov_center_x + half_w, self.fov_center_y + half_w

        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#38bdf8", width=2, tags="fov_element")
        self.canvas.create_line(self.fov_center_x - 6, self.fov_center_y, self.fov_center_x + 6, self.fov_center_y,
                                fill="#38bdf8", tags="fov_element")
        self.canvas.create_line(self.fov_center_x, self.fov_center_y - 6, self.fov_center_x, self.fov_center_y + 6,
                                fill="#38bdf8", tags="fov_element")

        self.fov_sz_lbl.config(text=f"Estimated Frame Width: {fov_deg * 60.0:.1f} arcminutes (2K grid)")

    def on_canvas_interaction(self, event):
        # Bound coordinates safely inside visual boundaries
        self.fov_center_x = max(10, min(event.x, 350))
        self.fov_center_y = max(10, min(event.y, 350))

        # Redraw viewport crosshair frames
        self.draw_schematic_elements()
        self.calculate_live_fov_coordinates()

    def draw_schematic_elements(self):
        self.canvas.delete("transit_element")
        self.canvas.delete("fov_element")

        # Draw primary solar disc frame body
        self.canvas.create_oval(self.canvas_center_x - self.sun_radius_px, self.canvas_center_y - self.sun_radius_px,
                                self.canvas_center_x + self.sun_radius_px, self.canvas_center_y + self.sun_radius_px,
                                fill="#fef08a", outline="#eab308", width=2, tags="transit_element")

        # Overlay mapped flight path traces if populated
        if self.path_points:
            for i in range(len(self.path_points) - 1):
                pt1 = self.path_points[i]
                pt2 = self.path_points[i + 1]
                self.canvas.create_line(pt1[0], pt1[1], pt2[0], pt2[1], fill="#ef4444", width=2, tags="transit_element")

            # Render directional entry markers
            start_pt = self.path_points[0]
            self.canvas.create_oval(start_pt[0] - 4, start_pt[1] - 4, start_pt[0] + 4, start_pt[1] + 4, fill="#22c55e",
                                    outline="#ffffff", tags="transit_element")

        self.draw_fov_box()

    def on_table_row_selected(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        row_values = self.tree.item(selected_item[0])["values"]
        norad_id = int(row_values[1])

        matched_transit = None
        for res in self.current_results:
            if int(res['norad_id']) == norad_id:
                matched_transit = res
                break

        if not matched_transit or norad_id not in self.loaded_satellites:
            return

        sat_obj = self.loaded_satellites[norad_id]
        self.selected_transit_data = matched_transit
        self.calculate_path_projection(sat_obj, matched_transit)

    def calculate_path_projection(self, sat_obj, transit_meta):
        ts = load.timescale()
        eph = load('de421.bsp')
        sun, earth = eph['sun'], eph['earth']

        observer = wgs84.latlon(self.lat_var.get(), self.lon_var.get())
        observer_on_earth = earth + observer

        t_start = transit_meta['transit_start']
        t_end = transit_meta['transit_end']

        # Calculate precise duration
        duration = (t_end.utc_datetime() - t_start.utc_datetime()).total_seconds()
        t_center = t_start + timedelta(seconds=duration / 2.0)

        # Base reference coordinates at the center of the transit (strictly preserved)
        sun_pos = observer_on_earth.at(t_center).observe(sun).apparent()
        ra, dec, _ = sun_pos.radec()
        self.sun_base_ra = ra.hours
        self.sun_base_dec = dec.degrees

        self.sun_coord_lbl.config(
            text=f"Sun Center RA: {self.format_ra(self.sun_base_ra)} | DEC: {self.format_dec(self.sun_base_dec)}"
        )

        # Time buffer for line extension
        buffer_sec = max(2.0, duration * 0.5)
        plot_duration = duration + (2 * buffer_sec)
        sample_steps = 45
        seconds_array = np.linspace(0, plot_duration, sample_steps)

        plot_start_tt = t_start.tt - (buffer_sec / 86400.0)
        time_points = ts.tt_jd(plot_start_tt + (seconds_array / 86400.0))

        sun_positions = observer_on_earth.at(time_points).observe(sun).apparent()
        sat_positions = (sat_obj - observer).at(time_points)

        # Convert Sun center reference to radians for spherical trigonometry
        ra0 = np.radians(self.sun_base_ra * 15.0)
        dec0 = np.radians(self.sun_base_dec)

        self.path_points = []
        for i in range(sample_steps):
            sat_ra_obj, sat_dec_obj, _ = sat_positions[i].radec()

            ra_i = np.radians(sat_ra_obj.hours * 15.0)
            dec_i = np.radians(sat_dec_obj.degrees)

            # Gnomonic Tangent Projection
            cos_c = np.sin(dec0) * np.sin(dec_i) + np.cos(dec0) * np.cos(dec_i) * np.cos(ra_i - ra0)
            x_gnomonic = (np.cos(dec_i) * np.sin(ra_i - ra0)) / cos_c
            y_gnomonic = (np.cos(dec0) * np.sin(dec_i) - np.sin(dec0) * np.cos(dec_i) * np.cos(ra_i - ra0)) / cos_c

            delta_ra_deg = np.degrees(x_gnomonic)
            delta_dec_deg = np.degrees(y_gnomonic)

            # Canvas Projection (Mapping East to Left, North to Up)
            px_x = self.canvas_center_x - (delta_ra_deg / self.deg_per_px)
            px_y = self.canvas_center_y - (delta_dec_deg / self.deg_per_px)

            self.path_points.append((px_x, px_y))

        self.draw_schematic_elements()
        self.calculate_live_fov_coordinates()

    def calculate_live_fov_coordinates(self):
        if self.sun_base_ra == 0.0 and self.sun_base_dec == 0.0:
            return

        # 1. Calculate pixel displacement from the center of the Sun
        dx_px = self.fov_center_x - self.canvas_center_x
        dy_px = self.fov_center_y - self.canvas_center_y

        # 2. Convert pixels back to Gnomonic plane coordinates (radians)
        # Recall canvas inversions: left is +RA (negative dx_px), up is +DEC (negative dy_px)
        delta_ra_deg = -dx_px * self.deg_per_px
        delta_dec_deg = -dy_px * self.deg_per_px

        x = np.radians(delta_ra_deg)
        y = np.radians(delta_dec_deg)

        rho = np.sqrt(x ** 2 + y ** 2)
        if rho == 0:
            live_ra = self.sun_base_ra
            live_dec = self.sun_base_dec
        else:
            c = np.arctan(rho)
            ra0 = np.radians(self.sun_base_ra * 15.0)
            dec0 = np.radians(self.sun_base_dec)

            # 3. Exact Inverse Gnomonic Transformation equations
            dec_rad = np.arcsin(np.cos(c) * np.sin(dec0) + (y * np.sin(c) * np.cos(dec0)) / rho)
            ra_rad = ra0 + np.arctan2(x * np.sin(c), rho * np.cos(dec0) * np.cos(c) - y * np.sin(dec0) * np.sin(c))

            live_ra = np.degrees(ra_rad) / 15.0 % 24.0
            live_dec = np.degrees(dec_rad)

        self.fov_coord_lbl.config(text=f"FOV Center RA: {self.format_ra(live_ra)} | DEC: {self.format_dec(live_dec)}")

    def format_ra(self, decimal_hours):
        h = int(decimal_hours)
        m = int((decimal_hours - h) * 60)
        s = (decimal_hours - h - m / 60.0) * 3600
        return f"{h:02d}h{m:02d}m{s:04.1f}s"

    def format_dec(self, decimal_degrees):
        sign = "+" if decimal_degrees >= 0 else "-"
        abs_deg = abs(decimal_degrees)
        d = int(abs_deg)
        m = int((abs_deg - d) * 60)
        s = (abs_deg - d - m / 60.0) * 3600
        return f"{sign}{d:02d}°{m:02d}'{s:04.1f}\""

    def configure_datetime_entry(self, entry):
        entry.current_segment = None
        segments = [(0, 4), (5, 7), (8, 10), (11, 13), (14, 16)]

        def select_segment(idx):
            if 0 <= idx < len(segments):
                entry.current_segment = idx
                start, end = segments[idx]
                entry.selection_range(start, end)
                entry.icursor(start)
                entry.focus_set()

        def on_focus_in(event):
            if not getattr(entry, '_clicked', False):
                entry.after(10, lambda: select_segment(0))

        def on_button_down(event):
            entry._clicked = True

        def on_click(event):
            def handle_click():
                cursor_pos = entry.index(tk.INSERT)
                for idx, (start, end) in enumerate(segments):
                    if start <= cursor_pos <= end:
                        select_segment(idx)
                        entry._clicked = False
                        return
                if cursor_pos < 5:
                    select_segment(0)
                elif cursor_pos < 8:
                    select_segment(1)
                elif cursor_pos < 11:
                    select_segment(2)
                elif cursor_pos < 14:
                    select_segment(3)
                else:
                    select_segment(4)
                entry._clicked = False

            entry.after(10, handle_click)

        def on_tab(event):
            if entry.current_segment is None: return select_segment(0) or "break"
            if entry.current_segment < 4: return select_segment(entry.current_segment + 1) or "break"
            return None

        def on_shift_tab(event):
            if entry.current_segment is None: return select_segment(4) or "break"
            if entry.current_segment > 0: return select_segment(entry.current_segment - 1) or "break"
            return None

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", lambda e: setattr(entry, 'current_segment', None))
        entry.bind("<Button-1>", on_button_down)
        entry.bind("<ButtonRelease-1>", on_click)
        entry.bind("<Tab>", on_tab)
        entry.bind("<Shift-Tab>", on_shift_tab)

    def sort_column(self, col_id):
        data = [(self.tree.set(child, col_id), child) for child in self.tree.get_children("")]
        ascending = self.sort_ascending[col_id]
        try:
            data.sort(key=lambda t: float(t[0]), reverse=not ascending)
        except ValueError:
            data.sort(key=lambda t: t[0], reverse=not ascending)

        for index, (_, child) in enumerate(data): self.tree.move(child, "", index)
        for c_id, c_name in self.columns_dict.items():
            self.tree.heading(c_id, text=c_name + ("  ▲" if ascending else "  ▼") if c_id == col_id else c_name)
        self.sort_ascending[col_id] = not ascending

    def parse_gcat_dimension(self, dim_str, span_str):
        sizes = []
        if span_str and span_str.strip() and span_str.strip() != '-':
            try:
                clean = ''.join(c for c in span_str if c.isdigit() or c == '.')
                if clean: sizes.append(float(clean))
            except ValueError:
                pass
        if dim_str and dim_str.strip() and dim_str.strip() != '-':
            parts, current = [], []
            for char in dim_str.lower().strip():
                if char in '0123456789.':
                    current.append(char)
                elif char in 'x*/ ' and current:
                    parts.append(''.join(current));
                    current = []
            if current: parts.append(''.join(current))
            for p in parts:
                try:
                    sizes.append(float(p))
                except ValueError:
                    pass
        return max(sizes) / 2.0 if sizes else None

    def start_calculation(self):
        try:
            lat, lon = self.lat_var.get(), self.lon_var.get()
            focal_len, pixel_size = self.focal_var.get(), self.pixel_var.get()
            hbr_default = self.hbr_var.get()
            selected_tz = ZoneInfo(self.tz_var.get().strip())
            start_time = datetime.strptime(self.start_var.get(), "%Y-%m-%d %H:%M").replace(tzinfo=selected_tz)
            end_time = datetime.strptime(self.end_var.get(), "%Y-%m-%d %H:%M").replace(tzinfo=selected_tz)
        except Exception:
            messagebox.showerror("Error",
                                 "Please cross check geographical coordinate boundaries, timezone parameters, or clock patterns.")
            return

        selected_groups = [k for k, v in self.check_vars.items() if v.get()]
        custom_target_str = self.custom_target_var.get().strip()

        if not selected_groups and not custom_target_str:
            messagebox.showwarning("Warning", "Please select at least one tracking configuration framework block.")
            return

        self.calc_btn.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.path_points = []
        self.draw_empty_canvas()
        self.status_lbl.config(text="Processing orbit geometry metrics...", foreground="#d97706")

        threading.Thread(target=self.run_logic, args=(
            lat, lon, start_time, end_time, focal_len, pixel_size, hbr_default, selected_groups, selected_tz,
            custom_target_str)).start()

    def run_logic(self, lat, lon, start_time, end_time, focal_len, pixel_size_um, hbr_default, selected_groups,
                  selected_tz, custom_target_str):
        try:
            if not os.path.exists(GCAT_FILENAME):
                try:
                    req = urllib.request.Request(GCAT_URL, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response, open(GCAT_FILENAME, 'wb') as out_file:
                        out_file.write(response.read())
                except Exception as e:
                    print(e)

            all_sats = []
            for group_key in selected_groups:
                url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group_key}&FORMAT=tle"
                all_sats.extend(load.tle_file(url, filename=CELESTRAK_GROUPS[group_key]['file']))

            if custom_target_str:
                for token in [t.strip() for t in custom_target_str.split(",") if t.strip()]:
                    if token.isdigit():
                        url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={token}&FORMAT=tle"
                        fname = f"custom_norad_{token}.txt"
                    else:
                        url = f"https://celestrak.org/NORAD/elements/gp.php?NAME={urllib.parse.quote(token)}&FORMAT=tle"
                        fname = f"custom_name_{''.join(c for c in token if c.isalnum())}.txt"
                    try:
                        all_sats.extend(load.tle_file(url, filename=fname))
                    except Exception:
                        pass

            self.loaded_satellites = {sat.model.satnum: sat for sat in all_sats}
            self.current_results = self.find_transits(list(self.loaded_satellites.values()), start_time, end_time, lat,
                                                      lon)
            transit_ids = {int(r['norad_id']) for r in self.current_results}

            gcat_database = {}
            if os.path.exists(GCAT_FILENAME) and transit_ids:
                try:
                    with open(GCAT_FILENAME, "r", encoding="utf-8", errors="ignore") as f:
                        header = []
                        for line in f:
                            if not line.strip(): continue
                            if line.startswith("#"):
                                if "satcat" in line.lower(): header = [h.strip().lower() for h in
                                                                       line.lstrip("#").strip().split("\t")]
                                continue
                            if not header: continue
                            cols = line.split("\t")
                            if len(cols) < len(header): cols += [""] * (len(header) - len(cols))
                            row_dict = dict(zip(header, cols))
                            try:
                                nid = int(row_dict.get("satcat", ""))
                                if nid in transit_ids:
                                    hbr = self.parse_gcat_dimension(row_dict.get("dim", ""), row_dict.get("span", ""))
                                    if hbr is not None: gcat_database[nid] = hbr
                            except ValueError:
                                pass
                except Exception:
                    pass

            ui_rows = []
            for r in self.current_results:
                nid = int(r['norad_id'])
                hbr = gcat_database.get(nid, hbr_default)
                pixels = ((hbr * 2) * focal_len) / (r['range_km'] * pixel_size_um)
                t_start = r['transit_start'].utc_datetime().astimezone(selected_tz).strftime('%Y-%m-%d %H:%M:%S.%f')[
                          :-3]
                t_end = r['transit_end'].utc_datetime().astimezone(selected_tz).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                ui_rows.append((
                    r['name'], r['norad_id'], t_start, t_end, f"{r['duration']:.2f}", f"{r['altitude']:.1f}",
                    f"{hbr:.1f}", f"{pixels:.1f}"))

            self.root.after(0, self.update_table, ui_rows)
        except Exception as e:
            self.root.after(0, self.show_error, str(e))

    def update_table(self, rows):
        for row in rows: self.tree.insert("", tk.END, values=row)
        self.status_lbl.config(text=f"Done! Found {len(rows)} execution target arrays.", foreground=self.accent_green)
        self.calc_btn.config(state=tk.NORMAL)
        self.sort_column("start")

    def show_error(self, err):
        messagebox.showerror("Error", err)
        self.status_lbl.config(text="Execution exception break.", foreground="#ef4444")
        self.calc_btn.config(state=tk.NORMAL)

    def export_to_csv(self):
        children = self.tree.get_children()
        if not children: return
        fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not fp: return
        try:
            with open(fp, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([self.columns_dict[c] for c in self.tree["columns"]])
                for child in children: writer.writerow(self.tree.item(child)["values"])
        except Exception:
            pass

    def export_schematic(self):
        if not self.path_points or not self.selected_transit_data:
            messagebox.showwarning("Warning", "Please select a transit event row from the data matrix first.")
            return

        # --- FIX: PROPER INDENTATION LEVEL ---
        selected_tz = ZoneInfo(self.tz_var.get().strip())

        # Format timestamps exactly as requested with colons and hyphens: YYYY-MM-DD:HH-MM
        fn_start = self.selected_transit_data['transit_start'].utc_datetime().astimezone(selected_tz).strftime(
            '%Y-%m-%d_%H-%M')
        fn_end = self.selected_transit_data['transit_end'].utc_datetime().astimezone(selected_tz).strftime(
            '%Y-%m-%d_%H-%M')

        # Clean up satellite name to remove invalid file characters
        clean_sat_name = "".join(
            c for c in str(self.selected_transit_data['name']) if c.isalnum() or c in ('_', '-')).strip()

        # Combine into the requested pattern: satellite_starttransit_endtransit.png
        default_filename = f"{clean_sat_name}_{fn_start}_{fn_end}.png"

        # Ask the user for a save path, pre-filling it with the default filename
        fp = filedialog.asksaveasfilename(
            initialfile=default_filename,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")]
        )
        # --------------------------------------

        if not fp:
            return

        try:
            from PIL import Image, ImageDraw
        except ImportError:
            messagebox.showerror("Error",
                                 "The 'Pillow' library is required to export PNG images.\nInstall it using: pip install pillow")
            return

        # 1. Initialize image context template matching visual constraints
        img = Image.new("RGB", (360, 360), "#0f172a")
        draw = ImageDraw.Draw(img)

        # 2. Render solar circle mass
        draw.ellipse([self.canvas_center_x - self.sun_radius_px, self.canvas_center_y - self.sun_radius_px,
                      self.canvas_center_x + self.sun_radius_px, self.canvas_center_y + self.sun_radius_px],
                     fill="#fef08a", outline="#eab308", width=2)

        # 3. Project trajectory traces
        if self.path_points:
            for i in range(len(self.path_points) - 1):
                pt1 = self.path_points[i]
                pt2 = self.path_points[i + 1]
                draw.line([pt1[0], pt1[1], pt2[0], pt2[1]], fill="#ef4444", width=2)

            start_pt = self.path_points[0]
            draw.ellipse([start_pt[0] - 4, start_pt[1] - 4, start_pt[0] + 4, start_pt[1] + 4], fill="#22c55e",
                         outline="#ffffff", width=1)

        # 4. Synthesize FOV bounding frames
        focal_len = max(10.0, self.focal_var.get())
        pixel_um = max(0.1, self.pixel_var.get())
        fov_rad = (2000.0 * pixel_um * 1e-3) / focal_len
        fov_deg = np.degrees(fov_rad)
        box_px = fov_deg / self.deg_per_px
        box_px = max(12.0, min(box_px, 600.0))
        half_w = box_px / 2.0
        x0, y0 = self.fov_center_x - half_w, self.fov_center_y - half_w
        x1, y1 = self.fov_center_x + half_w, self.fov_center_y + half_w
        draw.rectangle([x0, y0, x1, y1], outline="#38bdf8", width=2)
        draw.line([self.fov_center_x - 6, self.fov_center_y, self.fov_center_x + 6, self.fov_center_y], fill="#38bdf8",
                  width=1)
        draw.line([self.fov_center_x, self.fov_center_y - 6, self.fov_center_x, self.fov_center_y + 6], fill="#38bdf8",
                  width=1)

        # 5. Build dynamic string metadata blocks
        t_start_str = self.selected_transit_data['transit_start'].utc_datetime().astimezone(selected_tz).strftime(
            '%Y-%m-%d %H:%M:%S.%f')[:-3]
        t_end_str = self.selected_transit_data['transit_end'].utc_datetime().astimezone(selected_tz).strftime(
            '%Y-%m-%d %H:%M:%S.%f')[:-3]

        time_text = f"{t_start_str} - {t_end_str}"
        sat_text = str(self.selected_transit_data['name'])
        coord_text = str(self.fov_coord_lbl.cget("text"))

        # 6. Apply text transformations matching alignment rules
        draw.text((180, 12), time_text, fill="#ffffff", anchor="mt")
        draw.text((180, 28), sat_text, fill="#ffffff", anchor="mt")
        draw.text((180, 345), coord_text, fill="#ffffff", anchor="mb")

        img.save(fp)
        messagebox.showinfo("Success", f"Schematic exported successfully to:\n{os.path.basename(fp)}")

    def find_transits(self, satellites, start_time_local, end_time_local, lat, lon):
        start_utc = start_time_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_time_local.astimezone(ZoneInfo("UTC"))
        eph = load('de421.bsp')
        sun, earth = eph['sun'], eph['earth']
        ts = load.timescale()

        observer = wgs84.latlon(lat, lon)
        observer_on_earth = earth + observer
        duration_sec = int((end_utc - start_utc).total_seconds())
        if duration_sec <= 0: return []

        coarse_step = 10
        coarse_seconds = np.arange(0, duration_sec, coarse_step)
        coarse_times = ts.utc(start_utc.year, start_utc.month, start_utc.day, start_utc.hour, start_utc.minute,
                              start_utc.second + coarse_seconds)
        sun_pos_coarse = observer_on_earth.at(coarse_times).observe(sun).apparent()

        candidates = []
        for sat in satellites:
            sat_pos_coarse = (sat - observer).at(coarse_times)
            sep = sat_pos_coarse.separation_from(sun_pos_coarse).degrees
            for idx in np.where(sep < 3.0)[0]:
                candidates.append({'sat': sat, 't0': max(0, coarse_seconds[idx] - coarse_step),
                                   't1': min(duration_sec, coarse_seconds[idx] + coarse_step)})

        results = []
        fine_step = 0.1
        for cand in candidates:
            sat = cand['sat']
            fine_seconds = np.arange(cand['t0'], cand['t1'], fine_step)
            fine_times = ts.utc(start_utc.year, start_utc.month, start_utc.day, start_utc.hour, start_utc.minute,
                                start_utc.second + fine_seconds)
            app_sat = (sat - observer).at(fine_times)
            app_sun = observer_on_earth.at(fine_times).observe(sun).apparent()
            sep = app_sat.separation_from(app_sun).degrees
            transit_idx = np.where(sep < 0.266)[0]

            if len(transit_idx) > 0:
                min_idx = transit_idx[np.argmin(sep[transit_idx])]
                alt, _, dist = app_sat.altaz()
                if alt.degrees[min_idx] > 0:
                    results.append({
                        'name': sat.name, 'norad_id': sat.model.satnum,
                        'transit_start': fine_times[transit_idx[0]], 'transit_end': fine_times[transit_idx[-1]],
                        'duration': (fine_times[transit_idx[-1]].utc_datetime() - fine_times[
                            transit_idx[0]].utc_datetime()).total_seconds(),
                        'altitude': alt.degrees[min_idx], 'range_km': dist.km[min_idx]
                    })
        return list({r['norad_id']: r for r in results}.values())


if __name__ == '__main__':
    root = tk.Tk()
    app = TransitApp(root)
    root.mainloop()