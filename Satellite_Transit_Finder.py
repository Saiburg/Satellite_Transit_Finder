import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import numpy as np
import os
import csv
import urllib.request
from skyfield.api import load, wgs84
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# --- CONFIGURATION ---
DEFAULT_TZ_NAME = "Europe/Berlin"
GCAT_URL = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
GCAT_FILENAME = "satcat.tsv"

# Extended list of CelesTrak groups with focus on large/interesting objects
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
        self.root.title("Solar Transit Finder")
        self.root.geometry("1200x820")

        # Helper variable for sorting direction (True = Ascending, False = Descending)
        self.sort_ascending = {}

        # Styles Setup
        self.setup_styles()
        self.setup_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Color Palette
        self.bg_color = "#f8fafc"  # Slate 50 (App background)
        self.card_bg = "#ffffff"  # Pure white for containers
        self.primary_color = "#4f46e5"  # Indigo 600
        self.primary_hover = "#4338ca"  # Indigo 700
        self.secondary_color = "#0f172a"  # Slate 900 (Text & headers)
        self.border_color = "#e2e8f0"  # Slate 200
        self.accent_green = "#16a34a"  # Green 600

        self.root.configure(bg=self.bg_color)

        # Frame Styling
        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TLabelframe", background=self.card_bg, bordercolor=self.border_color, borderwidth=1,
                        relief="solid")
        style.configure("Card.TLabelframe.Label", background=self.card_bg, foreground=self.secondary_color,
                        font=("Segoe UI", 10, "bold"))

        # Label & Checkbutton Styling
        style.configure("TLabel", background=self.bg_color, foreground="#334155", font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=self.card_bg, foreground="#334155", font=("Segoe UI", 9))
        style.configure("Card.TCheckbutton", background=self.card_bg, foreground="#334155", font=("Segoe UI", 9))

        # Entry Styling
        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=self.border_color,
                        lightcolor=self.border_color, darkcolor=self.border_color)

        # Primary Action Button (Calculate)
        style.configure("Primary.TButton", background=self.primary_color, foreground="#ffffff", borderwidth=0,
                        font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.map("Primary.TButton", background=[("active", self.primary_hover), ("disabled", "#94a3b8")])

        # Secondary Action Button (Export)
        style.configure("Secondary.TButton", background="#ffffff", foreground=self.primary_color,
                        bordercolor=self.primary_color, borderwidth=1, font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.map("Secondary.TButton", background=[("active", "#f1f5f9")])

        # Treeview Styling
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26, background="#ffffff", fieldbackground="#ffffff",
                        gridcolor=self.border_color)
        style.configure("Treeview.Heading", background=self.secondary_color, foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"), padding=5)
        style.map("Treeview.Heading", background=[("active", "#1e293b")])
        style.map("Treeview", background=[("selected", "#e0e7ff")], foreground=[("selected", "#1e1b4b")])

    def setup_ui(self):
        # Main Container with comfortable padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- SETTINGS (Upper Half) ---
        settings_frame = ttk.LabelFrame(main_frame, text=" Observation & Camera Parameters ", padding="15",
                                        style="Card.TLabelframe")
        settings_frame.pack(fill=tk.X, pady=(0, 15))

        # Grid-Layout for settings (Adding takefocus=False to make only Time fields tabable)
        # 1. Location
        ttk.Label(settings_frame, text="Latitude (Lat):", style="Card.TLabel").grid(row=0, column=0, sticky=tk.W,
                                                                                    pady=4)
        self.lat_var = tk.DoubleVar(value=49.8728)  # Darmstadt
        ttk.Entry(settings_frame, textvariable=self.lat_var, width=15, takefocus=False).grid(row=0, column=1, padx=5,
                                                                                             pady=4)

        ttk.Label(settings_frame, text="Longitude (Lon):", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W,
                                                                                     pady=4)
        self.lon_var = tk.DoubleVar(value=8.6512)  # Darmstadt
        ttk.Entry(settings_frame, textvariable=self.lon_var, width=15, takefocus=False).grid(row=1, column=1, padx=5,
                                                                                             pady=4)

        # 2. Timezone & Time
        self.tz_var = tk.StringVar(value=DEFAULT_TZ_NAME)
        ttk.Label(settings_frame, text="Timezone (IANA):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W,
                                                                                     pady=4)
        ttk.Entry(settings_frame, textvariable=self.tz_var, width=15, takefocus=False).grid(row=2, column=1, padx=5,
                                                                                            pady=4)

        # Initial timezone parsing for default parameters
        try:
            tz = ZoneInfo(DEFAULT_TZ_NAME)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        start_default = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end_default = now.replace(hour=12, minute=0, second=0, microsecond=0)

        # --- TABABLE TIME WINDOWS ---
        ttk.Label(settings_frame, text="Start Time (YYYY-MM-DD HH:MM):", style="Card.TLabel").grid(row=0, column=2,
                                                                                                   sticky=tk.W,
                                                                                                   padx=(30, 0), pady=4)
        self.start_var = tk.StringVar(value=start_default.strftime('%Y-%m-%d %H:%M'))
        self.start_entry = ttk.Entry(settings_frame, textvariable=self.start_var, width=22, takefocus=True)
        self.start_entry.grid(row=0, column=3, padx=5, pady=4)

        ttk.Label(settings_frame, text="End Time (YYYY-MM-DD HH:MM):", style="Card.TLabel").grid(row=1, column=2,
                                                                                                 sticky=tk.W,
                                                                                                 padx=(30, 0), pady=4)
        self.end_var = tk.StringVar(value=end_default.strftime('%Y-%m-%d %H:%M'))
        self.end_entry = ttk.Entry(settings_frame, textvariable=self.end_var, width=22, takefocus=True)
        self.end_entry.grid(row=1, column=3, padx=5, pady=4)

        # Configure custom focus behavior on time inputs
        self.configure_datetime_entry(self.start_entry)
        self.configure_datetime_entry(self.end_entry)

        # 3. Telescope & Camera
        ttk.Label(settings_frame, text="Focal Length (mm):", style="Card.TLabel").grid(row=0, column=4, sticky=tk.W,
                                                                                       padx=(30, 0), pady=4)
        self.focal_var = tk.DoubleVar(value=1000.0)
        ttk.Entry(settings_frame, textvariable=self.focal_var, width=12, takefocus=False).grid(row=0, column=5, padx=5,
                                                                                               pady=4)

        ttk.Label(settings_frame, text="Pixel Size (µm):", style="Card.TLabel").grid(row=1, column=4, sticky=tk.W,
                                                                                     padx=(30, 0), pady=4)
        self.pixel_var = tk.DoubleVar(value=3.76)
        ttk.Entry(settings_frame, textvariable=self.pixel_var, width=12, takefocus=False).grid(row=1, column=5, padx=5,
                                                                                               pady=4)

        ttk.Label(settings_frame, text="Default Object HBR (m):", style="Card.TLabel").grid(row=2, column=4,
                                                                                            sticky=tk.W, padx=(30, 0),
                                                                                            pady=4)
        self.hbr_var = tk.DoubleVar(value=5.0)
        ttk.Entry(settings_frame, textvariable=self.hbr_var, width=12, takefocus=False).grid(row=2, column=5, padx=5,
                                                                                             pady=4)

        # --- CELESTRAK CHECKBOXES ---
        celestrak_frame = ttk.LabelFrame(main_frame, text=" CelesTrak Catalogues ", padding="15",
                                         style="Card.TLabelframe")
        celestrak_frame.pack(fill=tk.X, pady=(0, 15))

        self.check_vars = {}
        row, col = 0, 0
        for key, info in CELESTRAK_GROUPS.items():
            var = tk.BooleanVar(value=info["default"])
            self.check_vars[key] = var

            # Arrange in 4 columns
            ttk.Checkbutton(celestrak_frame, text=info["name"], variable=var, style="Card.TCheckbutton",
                            takefocus=False).grid(row=row,
                                                  column=col,
                                                  padx=12,
                                                  pady=5,
                                                  sticky=tk.W)
            col += 1
            if col > 3:
                col = 0
                row += 1

        # --- ACTION AREA (Buttons & Status) ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 12))

        self.calc_btn = ttk.Button(btn_frame, text="Calculate Transits", command=self.start_calculation,
                                   style="Primary.TButton", takefocus=False)
        self.calc_btn.pack(side=tk.LEFT)

        self.status_lbl = ttk.Label(btn_frame, text="Ready.", foreground=self.primary_color,
                                    font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(side=tk.LEFT, padx=20)

        # Export Button
        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_to_csv,
                                     style="Secondary.TButton", takefocus=False)
        self.export_btn.pack(side=tk.RIGHT)

        # --- TABLE ---
        self.columns_dict = {
            "name": "Name",
            "norad": "NORAD ID",
            "start": "Transit Start (Local)",
            "end": "Transit End (Local)",
            "duration": "Duration (s)",
            "alt": "Altitude (°)",
            "hbr": "HBR (m)",
            "pixels": "Size (Pixels)"
        }

        columns = tuple(self.columns_dict.keys())

        # Wrapped table inside a container frame to visually isolate its border
        table_container = ttk.Frame(main_frame)
        table_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", height=15, takefocus=False)

        # Configure headers & bind click event for sorting
        for col_id, col_name in self.columns_dict.items():
            self.tree.heading(col_id, text=col_name, command=lambda c=col_id: self.sort_column(c))
            self.sort_ascending[col_id] = True

        self.tree.column("name", width=180)
        self.tree.column("norad", width=80, anchor=tk.CENTER)
        self.tree.column("start", width=180, anchor=tk.CENTER)
        self.tree.column("end", width=180, anchor=tk.CENTER)
        self.tree.column("duration", width=85, anchor=tk.CENTER)
        self.tree.column("alt", width=85, anchor=tk.CENTER)
        self.tree.column("hbr", width=85, anchor=tk.CENTER)
        self.tree.column("pixels", width=105, anchor=tk.CENTER)

        # Clean scrollbar matching styling rules
        scrollbar = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def configure_datetime_entry(self, entry):
        """Sets up segmented keyboard Tab and Mouse-Click highlighting behaviors."""
        entry.current_segment = None

        # Character index spans for: [Year, Month, Day, Hour, Minute] in "YYYY-MM-DD HH:MM"
        segments = [
            (0, 4),  # Year
            (5, 7),  # Month
            (8, 10),  # Day
            (11, 13),  # Hour
            (14, 16)  # Minute
        ]

        def select_segment(idx):
            if 0 <= idx < len(segments):
                entry.current_segment = idx
                start, end = segments[idx]
                entry.selection_range(start, end)
                entry.icursor(start)
                entry.focus_set()

        def on_focus_in(event):
            # Only trigger segment-0 auto-focus if focus wasn't initiated by a direct mouse-click
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
                # Default selection boundary approximations if clicking near dividers
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
            if entry.current_segment is None:
                select_segment(0)
                return "break"
            if entry.current_segment < 4:
                select_segment(entry.current_segment + 1)
                return "break"
            else:
                entry.current_segment = None
                # Allow default Tab traversal to go to next Entry widget
                return None

        def on_shift_tab(event):
            if entry.current_segment is None:
                select_segment(4)
                return "break"
            if entry.current_segment > 0:
                select_segment(entry.current_segment - 1)
                return "break"
            else:
                entry.current_segment = None
                return None

        def on_focus_out(event):
            entry.current_segment = None
            entry._clicked = False

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        entry.bind("<Button-1>", on_button_down)
        entry.bind("<ButtonRelease-1>", on_click)
        entry.bind("<Tab>", on_tab)
        entry.bind("<Shift-Tab>", on_shift_tab)

    def sort_column(self, col_id):
        """Sorts the Treeview table based on the selected column."""
        data = [(self.tree.set(child, col_id), child) for child in self.tree.get_children("")]
        ascending = self.sort_ascending[col_id]

        try:
            data.sort(key=lambda t: float(t[0]), reverse=not ascending)
        except ValueError:
            data.sort(key=lambda t: t[0], reverse=not ascending)

        for index, (_, child) in enumerate(data):
            self.tree.move(child, "", index)

        for c_id, c_name in self.columns_dict.items():
            if c_id == col_id:
                direction_symbol = "  ▲" if ascending else "  ▼"
                self.tree.heading(c_id, text=c_name + direction_symbol)
            else:
                self.tree.heading(c_id, text=c_name)

        self.sort_ascending[col_id] = not ascending

    def parse_gcat_dimension(self, dim_str, span_str):
        """Extracts the maximum sizing metric from GCAT data strings to return an estimated HBR."""
        sizes = []

        # 1. Check Span field (typically represents maximum array span, e.g. 109.0)
        if span_str and span_str.strip() and span_str.strip() != '-':
            try:
                # Strip metadata markers like '?', '*', 'a'
                clean_span = ''.join(c for c in span_str if c.isdigit() or c == '.')
                if clean_span:
                    sizes.append(float(clean_span))
            except ValueError:
                pass

        # 2. Check Dim field (e.g. "1.2x1.5x2.2" or "4.5d" or "0.5")
        if dim_str and dim_str.strip() and dim_str.strip() != '-':
            clean_dim = dim_str.lower().strip()
            parts = []
            current_part = []
            for char in clean_dim:
                if char in '0123456789.':
                    current_part.append(char)
                elif char in 'x*/' or char.isspace():
                    if current_part:
                        parts.append(''.join(current_part))
                        current_part = []
            if current_part:
                parts.append(''.join(current_part))

            for p in parts:
                try:
                    sizes.append(float(p))
                except ValueError:
                    pass

        if sizes:
            max_dim = max(sizes)
            return max_dim / 2.0  # HBR is half of maximum dimension (radius)
        return None

    def start_calculation(self):
        try:
            lat = self.lat_var.get()
            lon = self.lon_var.get()
            focal_len = self.focal_var.get()
            pixel_size = self.pixel_var.get()
            hbr_default = self.hbr_var.get()

            # Retrieve and validate the timezone
            tz_str = self.tz_var.get().strip()
            try:
                selected_tz = ZoneInfo(tz_str)
            except ZoneInfoNotFoundError:
                messagebox.showerror("Error",
                                     f"The timezone '{tz_str}' was not found. Please enter a valid IANA timezone (e.g., Europe/Berlin, UTC, America/New_York).")
                return

            start_str = self.start_var.get()
            end_str = self.end_var.get()
            start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M").replace(tzinfo=selected_tz)
            end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M").replace(tzinfo=selected_tz)
        except ValueError:
            messagebox.showerror("Error",
                                 "Please check your input formats (especially Latitude/Longitude, focal variables, or Date/Time in YYYY-MM-DD HH:MM).")
            return

        selected_groups = [k for k, v in self.check_vars.items() if v.get()]
        if not selected_groups:
            messagebox.showwarning("Warning", "Please select at least one catalogue.")
            return

        self.calc_btn.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.status_lbl.config(text="Calculating geometry... (This might take a moment)",
                               foreground="#d97706")  # Amber 600

        thread = threading.Thread(
            target=self.run_logic,
            args=(lat, lon, start_time, end_time, focal_len, pixel_size, hbr_default, selected_groups, selected_tz)
        )
        thread.start()

    def run_logic(self, lat, lon, start_time, end_time, focal_len, pixel_size_um, hbr_default, selected_groups,
                  selected_tz):
        try:
            # 1. Download GCAT if it doesn't exist yet (approx. 15MB)
            if not os.path.exists(GCAT_FILENAME):
                self.root.after(0, lambda: self.status_lbl.config(
                    text="Downloading GCAT database (approx. 15MB, only once)...",
                    foreground="#d97706"
                ))
                try:
                    req = urllib.request.Request(GCAT_URL, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response, open(GCAT_FILENAME, 'wb') as out_file:
                        out_file.write(response.read())
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "GCAT Download Failed",
                        f"Could not retrieve GCAT database:\n{e}\n\nFalling back to default HBR parameters."
                    ))

            # 2. Fetch CelesTrak lists & calculate transit geometries first
            self.root.after(0, lambda: self.status_lbl.config(
                text="Calculating transit geometry...",
                foreground="#ef4444"  # Red 500
            ))

            all_sats = []
            for group_key in selected_groups:
                url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group_key}&FORMAT=tle"
                sats = load.tle_file(url, filename=CELESTRAK_GROUPS[group_key]['file'])
                all_sats.extend(sats)

            unique_sats_dict = {sat.model.satnum: sat for sat in all_sats}
            unique_sats = list(unique_sats_dict.values())

            results = self.find_transits(unique_sats, start_time, end_time, lat, lon)

            # Isolate matched transits to extract only their dimensions
            transit_norad_ids = {int(r['norad_id']) for r in results}

            # 3. Parse GCAT exclusively for the matched transiting satellites
            gcat_database = {}
            if os.path.exists(GCAT_FILENAME) and transit_norad_ids:
                self.root.after(0, lambda: self.status_lbl.config(
                    text="Extracting dimensions for transit satellites...",
                    foreground="#d97706"
                ))
                try:
                    with open(GCAT_FILENAME, "r", encoding="utf-8", errors="ignore") as f:
                        header = []
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("#"):
                                if "satcat" in line.lower():
                                    header_line = line.lstrip("#").strip()
                                    header = [h.strip().lower() for h in header_line.split("\t")]
                                continue
                            if not header:
                                continue

                            cols = line.split("\t")
                            if len(cols) < len(header):
                                cols += [""] * (len(header) - len(cols))

                            row_dict = dict(zip(header, cols))
                            satcat_id = row_dict.get("satcat", "").strip()
                            if satcat_id and satcat_id != "-":
                                try:
                                    norad_id = int(satcat_id)
                                    # Only parse dimensions if this object is on our transit list
                                    if norad_id in transit_norad_ids:
                                        dim_str = row_dict.get("dim", "")
                                        span_str = row_dict.get("span", "")
                                        hbr = self.parse_gcat_dimension(dim_str, span_str)
                                        if hbr is not None:
                                            gcat_database[norad_id] = hbr
                                except ValueError:
                                    pass
                except Exception as e:
                    print("Error parsing GCAT file:", e)

            # 4. Generate UI row payloads
            ui_rows = []
            for r in results:
                norad_id_int = int(r['norad_id'])
                hbr_used = gcat_database.get(norad_id_int, hbr_default)

                diameter_m = hbr_used * 2
                range_km = r['range_km']
                pixels = (diameter_m * focal_len) / (range_km * pixel_size_um)

                # Format local dates using the designated timezone
                t_start_loc = r['transit_start'].utc_datetime().astimezone(selected_tz).strftime(
                    '%Y-%m-%d %H:%M:%S.%f')[
                              :-3]
                t_end_loc = r['transit_end'].utc_datetime().astimezone(selected_tz).strftime('%Y-%m-%d %H:%M:%S.%f')[
                            :-3]

                ui_rows.append((
                    r['name'],
                    r['norad_id'],
                    t_start_loc,
                    t_end_loc,
                    f"{r['duration']:.2f}",
                    f"{r['altitude']:.1f}",
                    f"{hbr_used:.1f}",
                    f"{pixels:.1f}"
                ))

            self.root.after(0, self.update_table, ui_rows)

        except Exception as e:
            self.root.after(0, self.show_error, str(e))

    def update_table(self, rows):
        for row in rows:
            self.tree.insert("", tk.END, values=row)

        count = len(rows)
        self.status_lbl.config(text=f"Done! {count} Transit(s) found.", foreground=self.accent_green)
        self.calc_btn.config(state=tk.NORMAL)

        # Auto-sort by start time upon loading
        self.sort_column("start")

    def show_error(self, error_msg):
        messagebox.showerror("Error", f"An error occurred:\n{error_msg}")
        self.status_lbl.config(text="Error during calculation.", foreground="#ef4444")
        self.calc_btn.config(state=tk.NORMAL)

    def export_to_csv(self):
        """Exports the active contents of the Treeview table to a user-specified CSV location."""
        children = self.tree.get_children()
        if not children:
            messagebox.showwarning("No Data", "There are no transit records in the table to export.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Save Transits Table"
        )

        if not file_path:
            return  # Cancelled by user

        try:
            with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Write standard Headers
                headers = [self.columns_dict[col] for col in self.tree["columns"]]
                writer.writerow(headers)

                # Write rows
                for child in children:
                    row_values = self.tree.item(child)["values"]
                    writer.writerow(row_values)

            messagebox.showinfo("Export Successful", f"Database successfully exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save CSV file:\n{str(e)}")

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
        coarse_threshold = (1.2 * (coarse_step / 2.0)) + 2.0

        coarse_seconds = np.arange(0, duration_sec, coarse_step)
        coarse_times = ts.utc(
            start_utc.year, start_utc.month, start_utc.day,
            start_utc.hour, start_utc.minute, start_utc.second + coarse_seconds
        )

        sun_positions_coarse = observer_on_earth.at(coarse_times).observe(sun).apparent()
        candidates = []

        for sat in satellites:
            sat_positions_coarse = (sat - observer).at(coarse_times)
            separation = sat_positions_coarse.separation_from(sun_positions_coarse).degrees
            close_indices = np.where(separation < coarse_threshold)[0]

            for idx in close_indices:
                candidates.append({
                    'satellite': sat,
                    'sec_start': max(0, coarse_seconds[idx] - coarse_step),
                    'sec_end': min(duration_sec, coarse_seconds[idx] + coarse_step)
                })

        fine_step = 0.1
        results = []

        for cand in candidates:
            sat = cand['satellite']
            fine_seconds = np.arange(cand['sec_start'], cand['sec_end'], fine_step)
            fine_times = ts.utc(
                start_utc.year, start_utc.month, start_utc.day,
                start_utc.hour, start_utc.minute, start_utc.second + fine_seconds
            )

            apparent_sat = (sat - observer).at(fine_times)
            apparent_sun = observer_on_earth.at(fine_times).observe(sun).apparent()

            separation = apparent_sat.separation_from(apparent_sun).degrees
            transit_indices = np.where(separation < 0.266)[0]

            if len(transit_indices) > 0:
                min_sep_idx = transit_indices[np.argmin(separation[transit_indices])]

                t_start = fine_times[transit_indices[0]]
                t_end = fine_times[transit_indices[-1]]
                duration = (t_end.utc_datetime() - t_start.utc_datetime()).total_seconds()

                alt, az, distance = apparent_sat.altaz()
                dist_km = distance.km[min_sep_idx]
                peak_alt = alt.degrees[min_sep_idx]

                if peak_alt > 0:
                    results.append({
                        'name': sat.name,
                        'norad_id': sat.model.satnum,
                        'transit_start': t_start,
                        'transit_end': t_end,
                        'duration': duration,
                        'altitude': peak_alt,
                        'range_km': dist_km
                    })

        unique_results = {res['norad_id']: res for res in results}.values()
        return list(unique_results)


if __name__ == '__main__':
    root = tk.Tk()
    app = TransitApp(root)
    root.mainloop()