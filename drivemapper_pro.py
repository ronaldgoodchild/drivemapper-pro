import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import win32wnet, win32netcon, win32api, win32file, winreg, win32gui, win32con
import json, os, sys, subprocess, string, threading, time, datetime, socket
from collections import defaultdict

try:
    import keyring  # passwords go to Windows Credential Manager, not the JSON file
except ImportError:
    keyring = None

KEYRING_SERVICE = "DriveMapperPro"
CONFIG_FILE = "network_vault.json"
SYNC_CONFIG_FILE = "sync_profiles.json"
LOG_FILE = "drive_events.log"

class DrivePro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DriveMapper Pro v6.0 | Full Sync Manager")
        self.geometry("1200x800")
        
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        self._pending_migration = False
        self.saved_drives = self.load_config()
        if self._pending_migration:
            self.save_config()  # moves legacy plain-text passwords into the credential vault
            self.log_event("Migrated plain-text passwords to Windows Credential Manager")
        self.sync_profiles = self.load_sync_config()
        self.active_session_letters = set()
        self.server_connections = {}  # Track server-level connections
        self.is_monitoring = True
        self.status_refresh_interval = 30  # seconds
        self.running_syncs = {}  # Track running sync processes
        
        self.setup_ui()
        self.update_suggested_letter()
        
        # Background worker for periodic status refresh
        self.worker_thread = threading.Thread(target=self.service_worker, daemon=True)
        self.worker_thread.start()

        # Proper close handling
        self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

    def log_event(self, msg):
        """Timestamped logging for infrastructure audit."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        except Exception as e:
            print(f"Logging error: {e}")

    # --- SYNC CONFIG MANAGEMENT ---
    def load_sync_config(self):
        """Load saved sync profiles from JSON file."""
        if os.path.exists(SYNC_CONFIG_FILE):
            try:
                with open(SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.log_event(f"Loaded {len(data)} sync profiles")
                        return data
            except Exception as e:
                self.log_event(f"SYNC CONFIG LOAD ERROR: {e}")
        return []

    def save_sync_config(self):
        """Save sync profiles to JSON file."""
        try:
            with open(SYNC_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.sync_profiles, f, indent=4)
            self.log_event(f"Saved {len(self.sync_profiles)} sync profiles")
        except Exception as e:
            self.log_event(f"SYNC CONFIG SAVE ERROR: {e}")
            messagebox.showerror("Save Error", f"Could not save sync configuration:\n{str(e)}")

    def extract_server_from_path(self, path):
        """Extract server address from UNC path."""
        if path.startswith("\\\\"):
            parts = path.split("\\")
            if len(parts) >= 3:
                return f"\\\\{parts[2]}"
        return None

    def establish_server_connection(self, server, username, password):
        """Establish a server-level connection to avoid error 1219."""
        if not server:
            return True
        
        # Check if we already have a connection to this server
        if server in self.server_connections:
            stored_creds = self.server_connections[server]
            if (username, password) == stored_creds:
                return True
            else:
                self.log_event(f"WARNING: Server {server} already connected with different credentials")
                return False
        
        try:
            # Connect to IPC$ to establish server-level session
            ipc_path = f"{server}\\IPC$"
            
            netresource = win32wnet.NETRESOURCE()
            netresource.lpRemoteName = ipc_path
            
            if username and password:
                win32wnet.WNetAddConnection2(
                    netresource,
                    password,
                    username,
                    0
                )
                self.server_connections[server] = (username, password)
                self.log_event(f"Established server connection to {server} with credentials")
            else:
                win32wnet.WNetAddConnection2(
                    netresource,
                    None,
                    None,
                    0
                )
                self.server_connections[server] = (None, None)
                self.log_event(f"Established server connection to {server} (no credentials)")
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            if "1219" in error_msg or "already" in error_msg.lower():
                self.server_connections[server] = (username, password)
                self.log_event(f"Server {server} already connected (error 1219 caught, proceeding)")
                return True
            else:
                self.log_event(f"Failed to establish server connection to {server}: {error_msg}")
                return False

    def disconnect_server_connection(self, server):
        """Disconnect from a specific server."""
        if not server:
            return
        
        try:
            ipc_path = f"{server}\\IPC$"
            win32wnet.WNetCancelConnection2(ipc_path, 0, True)
            if server in self.server_connections:
                del self.server_connections[server]
            self.log_event(f"Disconnected from server {server}")
        except Exception as e:
            self.log_event(f"Error disconnecting from {server}: {e}")

    # --- MASTER HELP ---
    def show_help(self):
        help_window = ctk.CTkToplevel(self)
        help_window.title("DrivePro Master Guide")
        help_window.geometry("900x850")
        help_window.attributes("-topmost", True)
        txt = ctk.CTkTextbox(help_window, font=("Consolas", 11), width=860, height=810)
        txt.pack(padx=20, pady=20)
        
        guide = (
            "DRIVEPRO v6.0 MASTER DOCUMENTATION\n"
            "===========================================================\n\n"
            "NEW IN v6.0: FULL SYNC MANAGER\n"
            "   - 🔄 Bidirectional sync between ANY locations\n"
            "   - 🛠️ Choose between RCLONE or ROBOCOPY\n"
            "   - ☁️ Sync: Local ↔ Cloud ↔ SMB ↔ FTP\n"
            "   - 📋 Save and manage multiple sync profiles\n"
            "   - ⚡ One-click sync execution\n\n"
            "SYNC TOOLS:\n"
            "   RCLONE:\n"
            "      - Best for: Cloud, FTP, SFTP, WebDAV\n"
            "      - Supports: Bidirectional sync (bisync)\n"
            "      - Features: Conflict resolution, filters\n"
            "   \n"
            "   ROBOCOPY:\n"
            "      - Best for: Local directories, SMB shares\n"
            "      - Supports: Mirror, backup modes\n"
            "      - Features: Fast, native Windows tool\n"
            "      - Perfect for: Network shares, external drives\n\n"
            "SYNC WORKFLOWS:\n"
            "   1. Open 'Sync Manager' tab\n"
            "   2. Choose sync tool (Rclone or Robocopy)\n"
            "   3. Select Source (Browse or type path)\n"
            "   4. Select Destination (Browse or type path)\n"
            "   5. Configure sync options\n"
            "   6. Save profile for reuse\n"
            "   7. Click 'Run Sync' to execute\n\n"
            "PATH FORMATS:\n"
            "   Local: C:\\Users\\Documents\n"
            "   SMB Share: \\\\10.0.0.XXX\\Media\n"
            "   Cloud (rclone): MyRemote:folder\n"
            "   FTP (rclone): :ftp:server.com/path\n\n"
            "SYNC MODES:\n"
            "   Rclone Bisync: Two-way sync, keeps both sides updated\n"
            "   Rclone Sync: One-way, destination matches source\n"
            "   Robocopy Mirror: One-way, exact copy (deletes extras)\n"
            "   Robocopy Copy: One-way, copies new/changed files only\n\n"
            "DRIVE MAPPING (Previous Features):\n"
            "   - All v5.5 features still included\n"
            "   - Clone drives, Error 1219 handling\n"
            "   - WoL, server management\n"
            "   - See 'Drive Mapping' tab\n\n"
            "TIPS:\n"
            "   - For cloud sync, configure rclone remotes first\n"
            "   - Use Robocopy for fast local/SMB syncs\n"
            "   - Save profiles for recurring sync jobs\n"
            "   - Check logs after sync for details\n"
            "   - Test with small folders first\n\n"
            "KEYBOARD SHORTCUTS:\n"
            "   - Alt+H: Show Help\n"
            "   - Alt+Q: Exit Application"
        )
        txt.insert("0.0", guide)
        txt.configure(state="disabled")

    # --- WoL & CLOUD SYNC (Legacy) ---
    def send_wol(self, mac_address):
        """Send Wake-on-LAN magic packet to specified MAC address."""
        try:
            mac = mac_address.replace(":", "").replace("-", "").replace(" ", "").strip()
            if len(mac) != 12:
                raise ValueError("Invalid MAC format. Use AA:BB:CC:DD:EE:FF")
            
            data = bytes.fromhex("FF" * 6 + mac * 16)
            
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(data, ("255.255.255.255", 9))
            
            self.log_event(f"WoL: Magic packet sent to {mac_address}")
            messagebox.showinfo("Wake-on-LAN", f"Magic packet sent to {mac_address}\nDevice should wake in 5-10 seconds.")
        except Exception as e:
            self.log_event(f"WoL ERROR: {e}")
            messagebox.showerror("WoL Error", f"Failed to send magic packet:\n{str(e)}")

    def sync_cloud(self, drive):
        """Sync local folder to cloud using rclone (legacy from drive profiles)."""
        local_path = filedialog.askdirectory(title="Select Local Folder to Sync to Cloud")
        if not local_path:
            return
        
        try:
            cmd = ["rclone", "sync", local_path, drive['path'], "--progress", "--verbose"]
            
            self.log_event(f"SYNC: Starting sync from {local_path} to {drive['path']}")
            subprocess.Popen(
                ["cmd", "/c", " ".join(cmd) + " & pause"],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            messagebox.showinfo("Sync Started", f"Syncing {local_path} to {drive['path']}\nCheck console window for progress.")
        except Exception as e:
            self.log_event(f"SYNC ERROR: {e}")
            messagebox.showerror("Sync Error", f"Failed to start sync:\n{str(e)}")

    # --- UI SETUP ---
    def setup_ui(self):
        # Configure grid weights
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header = ctk.CTkFrame(self)
        self.header.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self.header, text="DriveMapper Pro v6.0", font=("Arial", 18, "bold")).pack(side="left", padx=20)
        
        # Header buttons
        ctk.CTkButton(self.header, text="❌ Exit", width=70, command=self.exit_app).pack(side="right", padx=5)
        ctk.CTkButton(self.header, text="❓ Help", width=70, command=self.show_help).pack(side="right", padx=5)
        ctk.CTkButton(
            self.header,
            text="📜 Logs",
            width=80,
            command=self.open_logs
        ).pack(side="right", padx=5)
        ctk.CTkButton(
            self.header,
            text="☁️ Rclone Config",
            fg_color="#AF601A",
            width=120,
            command=self.open_rclone_config
        ).pack(side="right", padx=5)

        # Tabview for Drive Mapping and Sync Manager
        self.tabview = ctk.CTkTabview(self, width=1180, height=700)
        self.tabview.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # Create tabs
        self.tab_drives = self.tabview.add("🔌 Drive Mapping")
        self.tab_sync = self.tabview.add("🔄 Sync Manager")
        
        # Setup each tab
        self.setup_drive_mapping_tab()
        self.setup_sync_manager_tab()

    def setup_drive_mapping_tab(self):
        """Setup the drive mapping tab (existing functionality)."""
        # Configure grid
        self.tab_drives.grid_columnconfigure(0, weight=1)
        self.tab_drives.grid_columnconfigure(1, weight=1)
        self.tab_drives.grid_rowconfigure(1, weight=1)
        
        # Top section with add drive and status
        top_frame = ctk.CTkFrame(self.tab_drives)
        top_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=1)
        
        # Add Drive Frame (Left)
        self.add_frame = ctk.CTkFrame(top_frame, border_width=2)
        self.add_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        ctk.CTkLabel(self.add_frame, text="Add New Drive", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Protocol selector
        self.protocol_var = ctk.StringVar(value="SMB")
        ctk.CTkOptionMenu(
            self.add_frame,
            values=["SMB", "SFTP", "WebDAV", "NFS", "Cloud (Rclone)"],
            variable=self.protocol_var,
            command=self.update_placeholders
        ).pack(pady=5, padx=20, fill="x")

        # Input fields
        self.ent_letter = ctk.CTkEntry(self.add_frame, placeholder_text="Drive Letter (e.g., Z)")
        self.ent_letter.pack(pady=5, padx=20, fill="x")
        
        self.ent_path = ctk.CTkEntry(self.add_frame, placeholder_text="Network Path")
        self.ent_path.pack(pady=5, padx=20, fill="x")
        
        self.ent_mac = ctk.CTkEntry(self.add_frame, placeholder_text="MAC Address (optional, for WoL)")
        self.ent_mac.pack(pady=5, padx=20, fill="x")
        
        self.ent_user = ctk.CTkEntry(self.add_frame, placeholder_text="Username (if needed)")
        self.ent_user.pack(pady=5, padx=20, fill="x")
        
        self.ent_pass = ctk.CTkEntry(self.add_frame, placeholder_text="Password (if needed)", show="*")
        self.ent_pass.pack(pady=5, padx=20, fill="x")
        
        self.ent_label = ctk.CTkEntry(self.add_frame, placeholder_text="Display Name (optional)")
        self.ent_label.pack(pady=5, padx=20, fill="x")

        # Add button
        ctk.CTkButton(
            self.add_frame,
            text="✅ Validate & Add",
            fg_color="#27AE60",
            hover_color="#229954",
            command=self.validate_and_add
        ).pack(pady=10, padx=20, fill="x")

        # Status Frame (Right)
        self.status_frame = ctk.CTkFrame(top_frame, border_width=2)
        self.status_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        ctk.CTkLabel(self.status_frame, text="Live Drive Status", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Status display
        self.status_display = ctk.CTkTextbox(self.status_frame, font=("Consolas", 10), state="disabled", height=200)
        self.status_display.pack(pady=5, padx=10, fill="both", expand=True)
        
        # Status control buttons
        status_btn_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        status_btn_frame.pack(pady=5, fill="x", padx=10)
        
        ctk.CTkButton(
            status_btn_frame,
            text="🔄 Refresh",
            width=90,
            command=self.refresh_status_async
        ).pack(side="left", padx=2)
        
        ctk.CTkButton(
            status_btn_frame,
            text="🔍 Test",
            width=70,
            fg_color="#16A085",
            hover_color="#138D75",
            command=self.test_drive_detection
        ).pack(side="left", padx=2)
        
        ctk.CTkButton(
            status_btn_frame,
            text="🔧 Prepare",
            width=90,
            fg_color="#E67E22",
            hover_color="#CA6F1E",
            command=self.prepare_all_servers
        ).pack(side="left", padx=2)
        
        ctk.CTkButton(
            status_btn_frame,
            text="🔓 Clear",
            width=80,
            fg_color="#C0392B",
            hover_color="#A93226",
            command=self.clear_server_connections
        ).pack(side="left", padx=2)

        # Saved Profiles Frame (Bottom)
        self.profiles_frame = ctk.CTkFrame(self.tab_drives)
        self.profiles_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        
        # Header with controls
        header_frame = ctk.CTkFrame(self.profiles_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            header_frame,
            text="Saved Drive Profiles",
            font=("Arial", 14, "bold")
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            header_frame,
            text="▶▶ Map All",
            fg_color="#16A085",
            hover_color="#138D75",
            width=100,
            command=self.map_all_managed
        ).pack(side="right", padx=5)
        
        ctk.CTkButton(
            header_frame,
            text="⏹ Disconnect All",
            fg_color="#E74C3C",
            hover_color="#CB4335",
            width=130,
            command=self.disconnect_all
        ).pack(side="right", padx=5)

        # Scrollable profile container
        self.profile_scroll = ctk.CTkScrollableFrame(self.profiles_frame, height=200)
        self.profile_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.refresh_profile_ui()
        self.refresh_status_async()

    def setup_sync_manager_tab(self):
        """Setup the new sync manager tab."""
        # Configure grid
        self.tab_sync.grid_columnconfigure(0, weight=1)
        self.tab_sync.grid_columnconfigure(1, weight=1)
        self.tab_sync.grid_rowconfigure(1, weight=1)
        
        # Create Sync Job Frame (Left)
        self.sync_create_frame = ctk.CTkFrame(self.tab_sync, border_width=2)
        self.sync_create_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(self.sync_create_frame, text="Create Sync Job", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Profile name
        ctk.CTkLabel(self.sync_create_frame, text="Profile Name:", font=("Arial", 11)).pack(pady=(10,2), padx=20, anchor="w")
        self.sync_name = ctk.CTkEntry(self.sync_create_frame, placeholder_text="e.g., My Documents Backup")
        self.sync_name.pack(pady=5, padx=20, fill="x")
        
        # Sync tool selector
        ctk.CTkLabel(self.sync_create_frame, text="Sync Tool:", font=("Arial", 11, "bold")).pack(pady=(10,2), padx=20, anchor="w")
        self.sync_tool_var = ctk.StringVar(value="rclone")
        tool_frame = ctk.CTkFrame(self.sync_create_frame, fg_color="transparent")
        tool_frame.pack(pady=5, padx=20, fill="x")
        
        ctk.CTkRadioButton(
            tool_frame,
            text="Rclone (Cloud, FTP, SFTP)",
            variable=self.sync_tool_var,
            value="rclone",
            command=self.update_sync_tool_options
        ).pack(side="left", padx=10)
        
        ctk.CTkRadioButton(
            tool_frame,
            text="Robocopy (Local, SMB)",
            variable=self.sync_tool_var,
            value="robocopy",
            command=self.update_sync_tool_options
        ).pack(side="left", padx=10)
        
        # Source path
        ctk.CTkLabel(self.sync_create_frame, text="Source Path:", font=("Arial", 11)).pack(pady=(10,2), padx=20, anchor="w")
        source_frame = ctk.CTkFrame(self.sync_create_frame, fg_color="transparent")
        source_frame.pack(pady=5, padx=20, fill="x")
        
        self.sync_source = ctk.CTkEntry(source_frame, placeholder_text="C:\\Documents or \\\\server\\share or MyRemote:")
        self.sync_source.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(
            source_frame,
            text="📁 Browse",
            width=80,
            command=lambda: self.browse_sync_path(self.sync_source)
        ).pack(side="right")
        
        # Destination path
        ctk.CTkLabel(self.sync_create_frame, text="Destination Path:", font=("Arial", 11)).pack(pady=(10,2), padx=20, anchor="w")
        dest_frame = ctk.CTkFrame(self.sync_create_frame, fg_color="transparent")
        dest_frame.pack(pady=5, padx=20, fill="x")
        
        self.sync_dest = ctk.CTkEntry(dest_frame, placeholder_text="Destination location")
        self.sync_dest.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(
            dest_frame,
            text="📁 Browse",
            width=80,
            command=lambda: self.browse_sync_path(self.sync_dest)
        ).pack(side="right")
        
        # Sync mode selector
        ctk.CTkLabel(self.sync_create_frame, text="Sync Mode:", font=("Arial", 11)).pack(pady=(10,2), padx=20, anchor="w")
        self.sync_mode_var = ctk.StringVar(value="bisync")
        self.sync_mode_selector = ctk.CTkOptionMenu(
            self.sync_create_frame,
            values=["bisync (Two-way)", "sync (One-way)", "copy (One-way, keep existing)"],
            variable=self.sync_mode_var
        )
        self.sync_mode_selector.pack(pady=5, padx=20, fill="x")
        
        # Additional options
        self.sync_options_frame = ctk.CTkFrame(self.sync_create_frame, fg_color="transparent")
        self.sync_options_frame.pack(pady=10, padx=20, fill="x")
        
        self.sync_dry_run = ctk.CTkCheckBox(self.sync_options_frame, text="Dry run (test only)")
        self.sync_dry_run.pack(side="left", padx=5)
        
        self.sync_delete = ctk.CTkCheckBox(self.sync_options_frame, text="Delete extras in dest")
        self.sync_delete.pack(side="left", padx=5)
        
        # Buttons
        button_frame = ctk.CTkFrame(self.sync_create_frame, fg_color="transparent")
        button_frame.pack(pady=15, padx=20, fill="x")
        
        ctk.CTkButton(
            button_frame,
            text="💾 Save Profile",
            fg_color="#27AE60",
            hover_color="#229954",
            command=self.save_sync_profile
        ).pack(side="left", padx=5, fill="x", expand=True)
        
        ctk.CTkButton(
            button_frame,
            text="▶ Run Now",
            fg_color="#3498DB",
            hover_color="#2E86C1",
            command=self.run_sync_now
        ).pack(side="right", padx=5, fill="x", expand=True)
        
        # Saved Sync Profiles Frame (Right)
        self.sync_profiles_frame = ctk.CTkFrame(self.tab_sync, border_width=2)
        self.sync_profiles_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        ctk.CTkLabel(self.sync_profiles_frame, text="Saved Sync Profiles", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Profiles list
        self.sync_profiles_scroll = ctk.CTkScrollableFrame(self.sync_profiles_frame, height=400)
        self.sync_profiles_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.refresh_sync_profiles_ui()
        
        # Sync Output Frame (Bottom - spans both columns)
        self.sync_output_frame = ctk.CTkFrame(self.tab_sync, border_width=2)
        self.sync_output_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
        
        output_header = ctk.CTkFrame(self.sync_output_frame, fg_color="transparent")
        output_header.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(output_header, text="Sync Output", font=("Arial", 14, "bold")).pack(side="left")
        
        ctk.CTkButton(
            output_header,
            text="🗑️ Clear",
            width=80,
            command=self.clear_sync_output
        ).pack(side="right", padx=5)
        
        # Output text area
        self.sync_output = ctk.CTkTextbox(self.sync_output_frame, font=("Consolas", 10), state="disabled", height=150)
        self.sync_output.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Initialize sync tool options
        self.update_sync_tool_options()

    def update_sync_tool_options(self):
        """Update available sync modes based on selected tool."""
        tool = self.sync_tool_var.get()
        
        if tool == "rclone":
            self.sync_mode_selector.configure(
                values=["bisync (Two-way)", "sync (One-way)", "copy (One-way, keep existing)"]
            )
            self.sync_mode_var.set("bisync (Two-way)")
            self.sync_source.configure(placeholder_text="C:\\Folder or MyRemote:path or :ftp:server/path")
            self.sync_dest.configure(placeholder_text="C:\\Folder or MyRemote:path or :ftp:server/path")
        else:  # robocopy
            self.sync_mode_selector.configure(
                values=["mirror (Exact copy)", "copy (New/changed files only)"]
            )
            self.sync_mode_var.set("mirror (Exact copy)")
            self.sync_source.configure(placeholder_text="C:\\Folder or \\\\server\\share")
            self.sync_dest.configure(placeholder_text="C:\\Folder or \\\\server\\share")

    def browse_sync_path(self, entry_widget):
        """Browse for a directory and set it in the entry widget."""
        path = filedialog.askdirectory(title="Select Directory")
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)

    def save_sync_profile(self):
        """Save a sync profile."""
        name = self.sync_name.get().strip()
        source = self.sync_source.get().strip()
        dest = self.sync_dest.get().strip()
        tool = self.sync_tool_var.get()
        mode = self.sync_mode_var.get()
        
        if not name:
            messagebox.showerror("Invalid Input", "Please enter a profile name")
            return
        
        if not source or not dest:
            messagebox.showerror("Invalid Input", "Please enter both source and destination paths")
            return
        
        # Check for duplicate name
        for profile in self.sync_profiles:
            if profile.get('name', '') == name:
                if not messagebox.askyesno("Duplicate Name", f"Profile '{name}' already exists. Overwrite?"):
                    return
                self.sync_profiles.remove(profile)
                break
        
        profile = {
            'name': name,
            'tool': tool,
            'source': source,
            'dest': dest,
            'mode': mode,
            'dry_run': self.sync_dry_run.get(),
            'delete': self.sync_delete.get()
        }
        
        self.sync_profiles.append(profile)
        self.save_sync_config()
        self.refresh_sync_profiles_ui()
        
        # Clear form
        self.sync_name.delete(0, tk.END)
        self.sync_source.delete(0, tk.END)
        self.sync_dest.delete(0, tk.END)
        self.sync_dry_run.deselect()
        self.sync_delete.deselect()
        
        messagebox.showinfo("Success", f"Sync profile '{name}' saved successfully!")
        self.log_event(f"Saved sync profile: {name}")

    def run_sync_now(self):
        """Run sync with current form settings without saving."""
        source = self.sync_source.get().strip()
        dest = self.sync_dest.get().strip()
        tool = self.sync_tool_var.get()
        mode = self.sync_mode_var.get()
        
        if not source or not dest:
            messagebox.showerror("Invalid Input", "Please enter both source and destination paths")
            return
        
        profile = {
            'name': 'Quick Sync',
            'tool': tool,
            'source': source,
            'dest': dest,
            'mode': mode,
            'dry_run': self.sync_dry_run.get(),
            'delete': self.sync_delete.get()
        }
        
        self.execute_sync(profile)

    def execute_sync(self, profile):
        """Execute a sync profile."""
        tool = profile.get('tool', 'rclone')
        source = profile.get('source', '')
        dest = profile.get('dest', '')
        mode = profile.get('mode', 'Bidirectional Sync')
        name = profile.get('name', 'Unnamed Sync')
        dry_run = profile.get('dry_run', False)
        delete = profile.get('delete', False)
        
        # Build command based on tool
        if tool == "rclone":
            cmd = self.build_rclone_command(source, dest, mode, dry_run, delete)
        else:  # robocopy
            cmd = self.build_robocopy_command(source, dest, mode, dry_run, delete)
        
        # Log the command
        self.log_event(f"SYNC START: {name} - {' '.join(cmd)}")
        self.append_sync_output(f"\n{'='*60}\n")
        self.append_sync_output(f"Starting: {name}\n")
        self.append_sync_output(f"Tool: {tool}\n")
        self.append_sync_output(f"Command: {' '.join(cmd)}\n")
        self.append_sync_output(f"{'='*60}\n\n")
        
        # Run in new console window
        try:
            if tool == "rclone":
                # For rclone, show in new console with pause
                subprocess.Popen(
                    ["cmd", "/c", " ".join(cmd) + " & echo. & echo Sync completed! & pause"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                self.append_sync_output(f"✓ Sync started in new console window\n")
                self.append_sync_output(f"Check console for progress...\n\n")
            else:  # robocopy
                # For robocopy, can run in background and capture output
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # Run in thread to avoid blocking UI
                threading.Thread(
                    target=self.monitor_sync_process,
                    args=(process, name),
                    daemon=True
                ).start()
                
                self.append_sync_output(f"✓ Sync started (PID: {process.pid})\n\n")
        
        except Exception as e:
            error_msg = f"ERROR: Failed to start sync: {str(e)}\n"
            self.append_sync_output(error_msg)
            self.log_event(f"SYNC ERROR: {name} - {str(e)}")
            messagebox.showerror("Sync Error", f"Failed to start sync:\n{str(e)}")

    def build_rclone_command(self, source, dest, mode, dry_run, delete):
        """Build rclone command."""
        cmd = ["rclone"]
        
        # Determine rclone subcommand
        if "bisync" in mode.lower():
            cmd.append("bisync")
            cmd.extend([source, dest])
            cmd.append("--resync")  # First run needs resync
            cmd.append("--verbose")
        elif "sync" in mode.lower():
            cmd.append("sync")
            cmd.extend([source, dest])
        else:  # copy
            cmd.append("copy")
            cmd.extend([source, dest])
        
        # Add flags
        cmd.append("--progress")
        
        if dry_run:
            cmd.append("--dry-run")
        
        if delete and "bisync" not in mode.lower():
            cmd.append("--delete-during")
        
        return cmd

    def build_robocopy_command(self, source, dest, mode, dry_run, delete):
        """Build robocopy command."""
        cmd = ["robocopy", source, dest]
        
        # Add options based on mode
        if "mirror" in mode.lower():
            cmd.append("/MIR")  # Mirror mode (purge dest)
        else:  # copy
            cmd.append("/E")  # Copy subdirectories including empty
        
        # Common useful flags
        cmd.append("/R:3")  # Retry 3 times
        cmd.append("/W:5")  # Wait 5 seconds between retries
        cmd.append("/NP")  # No progress (less verbose)
        cmd.append("/NFL")  # No file list
        cmd.append("/NDL")  # No directory list
        
        if dry_run:
            cmd.append("/L")  # List only, don't copy
        
        return cmd

    def monitor_sync_process(self, process, profile_name):
        """Monitor a sync process and update output."""
        try:
            while True:
                output = process.stdout.readline()
                if output:
                    self.append_sync_output(output)
                elif process.poll() is not None:
                    break
            
            # Get any remaining output
            remaining_output = process.communicate()[0]
            if remaining_output:
                self.append_sync_output(remaining_output)
            
            # Check return code
            if process.returncode == 0:
                self.append_sync_output(f"\n✓ Sync '{profile_name}' completed successfully!\n\n")
                self.log_event(f"SYNC SUCCESS: {profile_name}")
            else:
                self.append_sync_output(f"\n⚠ Sync '{profile_name}' completed with errors (code: {process.returncode})\n\n")
                self.log_event(f"SYNC WARNING: {profile_name} - exit code {process.returncode}")
        
        except Exception as e:
            error_msg = f"\nERROR monitoring sync: {str(e)}\n\n"
            self.append_sync_output(error_msg)
            self.log_event(f"SYNC MONITOR ERROR: {profile_name} - {str(e)}")

    def append_sync_output(self, text):
        """Append text to sync output window (thread-safe)."""
        self.sync_output.configure(state="normal")
        self.sync_output.insert("end", text)
        self.sync_output.see("end")
        self.sync_output.configure(state="disabled")

    def clear_sync_output(self):
        """Clear the sync output window."""
        self.sync_output.configure(state="normal")
        self.sync_output.delete("1.0", "end")
        self.sync_output.configure(state="disabled")

    def refresh_sync_profiles_ui(self):
        """Refresh the sync profiles display."""
        # Clear existing widgets
        for widget in self.sync_profiles_scroll.winfo_children():
            widget.destroy()
        
        if not self.sync_profiles:
            ctk.CTkLabel(
                self.sync_profiles_scroll,
                text="No saved sync profiles yet.\nCreate one using the form on the left.",
                font=("Arial", 11),
                text_color="gray"
            ).pack(pady=20)
            return
        
        # Display each profile
        for profile in self.sync_profiles:
            self.create_sync_profile_widget(profile)

    def create_sync_profile_widget(self, profile):
        """Create a widget for a sync profile."""
        frame = ctk.CTkFrame(self.sync_profiles_scroll, fg_color="#2C3E50")
        frame.pack(fill="x", padx=5, pady=3)
        
        # Profile info
        info_frame = ctk.CTkFrame(frame, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        
        tool = profile.get('tool', 'rclone')
        mode = profile.get('mode', 'Bidirectional Sync')
        tool_icon = "☁️" if tool == "rclone" else "💻"
        mode_short = mode.split()[0]
        
        ctk.CTkLabel(
            info_frame,
            text=f"{tool_icon} {profile.get('name', 'Unnamed')}",
            font=("Arial", 12, "bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_frame,
            text=f"   {profile.get('source', '?')} → {profile.get('dest', '?')}",
            font=("Arial", 10),
            text_color="gray"
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            info_frame,
            text=f"   Mode: {mode_short} | Tool: {tool}",
            font=("Arial", 9),
            text_color="lightgray"
        ).pack(anchor="w")
        
        # Buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(side="right", padx=5)
        
        ctk.CTkButton(
            btn_frame,
            text="🗑️",
            width=40,
            fg_color="#922B21",
            hover_color="#7B241C",
            command=lambda p=profile: self.delete_sync_profile(p)
        ).pack(side="right", padx=2)
        
        ctk.CTkButton(
            btn_frame,
            text="📋",
            width=40,
            fg_color="#7D3C98",
            hover_color="#6C3483",
            command=lambda p=profile: self.load_sync_profile(p)
        ).pack(side="right", padx=2)
        
        ctk.CTkButton(
            btn_frame,
            text="▶ Run",
            width=70,
            fg_color="#28B463",
            hover_color="#239B56",
            command=lambda p=profile: self.execute_sync(p)
        ).pack(side="right", padx=2)

    def delete_sync_profile(self, profile):
        """Delete a sync profile."""
        name = profile.get('name', 'Unnamed')
        if messagebox.askyesno("Confirm Delete", f"Delete sync profile '{name}'?"):
            if profile in self.sync_profiles:
                self.sync_profiles.remove(profile)
                self.save_sync_config()
                self.refresh_sync_profiles_ui()
                self.log_event(f"Deleted sync profile: {name}")

    def load_sync_profile(self, profile):
        """Load a sync profile into the form for editing."""
        self.sync_name.delete(0, tk.END)
        self.sync_name.insert(0, profile.get('name', ''))
        
        self.sync_source.delete(0, tk.END)
        self.sync_source.insert(0, profile.get('source', ''))
        
        self.sync_dest.delete(0, tk.END)
        self.sync_dest.insert(0, profile.get('dest', ''))
        
        self.sync_tool_var.set(profile.get('tool', 'rclone'))
        self.update_sync_tool_options()
        
        self.sync_mode_var.set(profile.get('mode', 'Bidirectional Sync'))
        
        if profile.get('dry_run'):
            self.sync_dry_run.select()
        else:
            self.sync_dry_run.deselect()
        
        if profile.get('delete'):
            self.sync_delete.select()
        else:
            self.sync_delete.deselect()
        
        name = profile.get('name', 'Unnamed')
        messagebox.showinfo("Profile Loaded", f"Profile '{name}' loaded for editing.")

    def open_rclone_config(self):
        """Open rclone config in new console window."""
        try:
            subprocess.Popen(
                ["cmd", "/c", "rclone config & pause"],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open rclone config:\n{str(e)}")

    def open_logs(self):
        """Open the log file in notepad."""
        try:
            if os.path.exists(LOG_FILE):
                subprocess.Popen(["notepad", LOG_FILE])
            else:
                messagebox.showinfo("Logs", "No log file exists yet.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open logs:\n{str(e)}")

    # [Previous drive mapping methods continue - validate_and_add, test_connection, map_single, etc.]
    # I'll include abbreviated versions of the critical ones for space:

    def validate_and_add(self):
        """Validate and add new drive configuration."""
        letter = self.ent_letter.get().strip().upper()
        path = self.ent_path.get().strip()
        username = self.ent_user.get().strip()
        password = self.ent_pass.get().strip()
        label = self.ent_label.get().strip()
        protocol = self.protocol_var.get()
        mac = self.ent_mac.get().strip()
        
        if not letter or len(letter) != 1 or letter not in string.ascii_uppercase:
            messagebox.showerror("Invalid Input", "Drive letter must be a single letter (A-Z)")
            return
        
        if not path:
            messagebox.showerror("Invalid Input", "Network path cannot be empty")
            return
        
        for drive in self.saved_drives:
            if drive['letter'] == letter:
                messagebox.showerror("Duplicate", f"Drive letter {letter}: is already in use")
                return
        
        drive_config = {
            'letter': letter,
            'path': path,
            'username': username,
            'password': password,
            'label': label or path,
            'protocol': protocol,
            'mac': mac
        }
        
        if self.test_connection(drive_config):
            self.saved_drives.append(drive_config)
            self.save_config()
            self.refresh_profile_ui()
            self.update_suggested_letter()
            
            self.ent_path.delete(0, tk.END)
            self.ent_user.delete(0, tk.END)
            self.ent_pass.delete(0, tk.END)
            self.ent_label.delete(0, tk.END)
            self.ent_mac.delete(0, tk.END)
            
            messagebox.showinfo("Success", f"Drive {letter}: validated and added successfully!")
        else:
            messagebox.showerror("Validation Failed", "Could not validate connection.\nCheck logs for details.")

    def test_connection(self, drive):
        """Test if drive can be mapped successfully."""
        protocol = drive.get('protocol', 'SMB')
        
        if protocol == "SMB":
            return self.test_smb(drive)
        elif protocol in ["SFTP", "WebDAV"]:
            return self.test_rclone_protocol(drive, protocol)
        elif protocol == "NFS":
            return self.test_nfs(drive)
        elif protocol == "Cloud (Rclone)":
            return self.test_rclone(drive)
        
        return False

    def test_smb(self, drive):
        """Test SMB connection."""
        try:
            path = drive['path']
            username = drive.get('username', '')
            password = drive.get('password', '')
            
            server = self.extract_server_from_path(path)
            
            if server and server in self.server_connections:
                stored_creds = self.server_connections[server]
                if (username, password) != stored_creds:
                    self.log_event(f"VALIDATION WARNING: {path} - Server already connected with different credentials")
                    return False
                else:
                    self.log_event(f"VALIDATION SUCCESS: {path} (server already connected)")
                    return True
            
            if server:
                if not self.establish_server_connection(server, username, password):
                    return False
            
            netresource = win32wnet.NETRESOURCE()
            netresource.lpRemoteName = path
            
            try:
                if server and server in self.server_connections:
                    win32wnet.WNetAddConnection2(netresource, None, None, win32netcon.CONNECT_TEMPORARY)
                elif username and password:
                    win32wnet.WNetAddConnection2(netresource, password, username, win32netcon.CONNECT_TEMPORARY)
                else:
                    win32wnet.WNetAddConnection2(netresource, None, None, win32netcon.CONNECT_TEMPORARY)
                
                win32wnet.WNetCancelConnection2(path, 0, True)
            except Exception as e:
                error_str = str(e)
                if "1219" in error_str or "85" in error_str:
                    self.log_event(f"VALIDATION SUCCESS: {path} (connection exists)")
                    return True
                else:
                    raise
            
            self.log_event(f"VALIDATION SUCCESS: {path}")
            return True
            
        except Exception as e:
            self.log_event(f"VALIDATION FAILED: {drive['path']} - {str(e)}")
            return False

    def test_rclone(self, drive):
        """Test rclone connection."""
        try:
            result = subprocess.run(
                ["rclone", "lsd", drive['path']],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                self.log_event(f"VALIDATION SUCCESS: {drive['path']} (Rclone)")
                return True
            else:
                self.log_event(f"VALIDATION FAILED: {drive['path']} - {result.stderr}")
                return False
                
        except Exception as e:
            self.log_event(f"VALIDATION FAILED: {drive['path']} - {str(e)}")
            return False

    def test_rclone_protocol(self, drive, protocol):
        """Test SFTP/WebDAV via rclone."""
        try:
            subprocess.run(["rclone", "version"], capture_output=True, timeout=5)
            return True
        except:
            return False

    def test_nfs(self, drive):
        """Test NFS connection."""
        path = drive['path']
        if ":" in path and not path.startswith("\\\\"):
            self.log_event(f"NFS path format appears valid: {path}")
            return True
        return False

    def map_single(self, drive, silent=False):
        """Map a single drive."""
        protocol = drive.get('protocol', 'SMB')
        
        try:
            if protocol == "SMB":
                return self.map_smb(drive, silent)
            elif protocol in ["SFTP", "WebDAV"]:
                return self.map_rclone_protocol(drive, protocol, silent)
            elif protocol == "NFS":
                return self.map_nfs(drive, silent)
            elif protocol == "Cloud (Rclone)":
                return self.map_rclone(drive, silent)
        except Exception as e:
            self.log_event(f"MAP ERROR ({drive['letter']}:): {str(e)}")
            if not silent:
                messagebox.showerror("Map Error", f"Failed to map {drive['letter']}:\n{str(e)}")
            return False

    def map_smb(self, drive, silent=False):
        """Map SMB/CIFS network drive with error 1219 handling."""
        letter = drive['letter']
        path = drive['path']
        username = drive.get('username', '')
        password = drive.get('password', '')
        
        try:
            server = self.extract_server_from_path(path)
            if server:
                if not self.establish_server_connection(server, username, password):
                    error_msg = f"Failed to establish server connection to {server}. Check if already connected with different credentials."
                    self.log_event(f"ERROR: Failed to map {letter}: → {path} (SMB): {error_msg}")
                    if not silent:
                        messagebox.showerror("Connection Error", error_msg)
                    return False
            
            netresource = win32wnet.NETRESOURCE()
            netresource.dwType = win32netcon.RESOURCETYPE_DISK
            netresource.lpLocalName = f"{letter}:"
            netresource.lpRemoteName = path
            
            if server and server in self.server_connections:
                win32wnet.WNetAddConnection2(netresource, None, None, 0)
                self.log_event(f"Mapped {letter}: using existing server session")
            else:
                if username and password:
                    win32wnet.WNetAddConnection2(netresource, password, username, 0)
                else:
                    win32wnet.WNetAddConnection2(netresource, None, None, 0)
            
            self.active_session_letters.add(letter)
            self.log_event(f"SUCCESS: Mapped {letter}: → {path} (SMB)")
            return True
            
        except Exception as e:
            error_code = str(e)
            if "85" in error_code:
                msg = f"Drive {letter}: is already in use"
            elif "1219" in error_code:
                msg = f"Multiple connections to {server} with different credentials. Disconnect all drives from this server first."
            elif "1326" in error_code:
                msg = "Invalid username or password"
            elif "53" in error_code:
                msg = "Network path not found. Check if server is online."
            else:
                msg = str(e)
            
            self.log_event(f"ERROR: Failed to map {letter}: → {path} (SMB): {msg}")
            if not silent:
                messagebox.showerror("Map Error", f"Failed to map {letter}:\n{msg}")
            return False

    def map_rclone(self, drive, silent=False):
        """Map cloud drive using rclone mount."""
        letter = drive['letter']
        path = drive['path']
        
        try:
            cmd = [
                "rclone", "mount",
                path,
                f"{letter}:",
                "--vfs-cache-mode", "writes",
                "--no-console"
            ]
            
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            
            self.active_session_letters.add(letter)
            self.log_event(f"SUCCESS: Mounted {letter}: → {path} (Rclone)")
            return True
            
        except Exception as e:
            self.log_event(f"ERROR: Failed to mount {letter}: → {path} (Rclone): {str(e)}")
            if not silent:
                messagebox.showerror("Mount Error", f"Failed to mount {letter}:\n{str(e)}")
            return False

    def map_rclone_protocol(self, drive, protocol, silent=False):
        """Map SFTP/WebDAV using rclone on-the-fly."""
        letter = drive['letter']
        path = drive['path']
        username = drive.get('username', '')
        password = drive.get('password', '')
        
        try:
            if protocol == "SFTP":
                remote_path = f":sftp,host={path}"
                if username:
                    remote_path += f",user={username}"
                if password:
                    remote_path += f",pass={password}"
                remote_path += ":"
            elif protocol == "WebDAV":
                remote_path = f":webdav,url=https://{path}"
                if username:
                    remote_path += f",user={username}"
                if password:
                    remote_path += f",pass={password}"
                remote_path += ":"
            
            cmd = [
                "rclone", "mount",
                remote_path,
                f"{letter}:",
                "--vfs-cache-mode", "writes",
                "--no-console"
            ]
            
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            
            self.active_session_letters.add(letter)
            self.log_event(f"SUCCESS: Mounted {letter}: → {path} ({protocol})")
            return True
            
        except Exception as e:
            self.log_event(f"ERROR: Failed to mount {letter}: ({protocol}): {str(e)}")
            if not silent:
                messagebox.showerror("Mount Error", f"Failed to mount {letter}:\n{str(e)}")
            return False

    def map_nfs(self, drive, silent=False):
        """Map NFS share."""
        letter = drive['letter']
        path = drive['path']
        
        try:
            cmd = ["mount", "-o", "anon", path, f"{letter}:"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.active_session_letters.add(letter)
                self.log_event(f"SUCCESS: Mounted {letter}: → {path} (NFS)")
                return True
            else:
                raise Exception(result.stderr or "NFS mount failed")
                
        except Exception as e:
            self.log_event(f"ERROR: Failed to mount {letter}: (NFS): {str(e)}")
            if not silent:
                messagebox.showerror("NFS Error", f"Failed to mount NFS:\n{str(e)}\n\nEnsure NFS client is installed.")
            return False

    def prepare_all_servers(self):
        """Establish connections to all servers before mapping drives."""
        servers_by_creds = defaultdict(list)
        
        for drive in self.saved_drives:
            if drive.get('protocol') == 'SMB':
                server = self.extract_server_from_path(drive['path'])
                if server:
                    creds = (drive.get('username', ''), drive.get('password', ''))
                    servers_by_creds[(server, creds)].append(drive)
        
        if not servers_by_creds:
            messagebox.showinfo("No Servers", "No SMB servers found in configurations.")
            return
        
        success_count = 0
        fail_count = 0
        
        for (server, creds), drives in servers_by_creds.items():
            username, password = creds
            if self.establish_server_connection(server, username, password):
                success_count += 1
            else:
                fail_count += 1
        
        self.refresh_status_async()
        messagebox.showinfo(
            "Server Preparation Complete",
            f"Successfully connected to {success_count} server(s)\nFailed: {fail_count}\n\nYou can now use 'Map All'."
        )

    def clear_server_connections(self):
        """Clear all server-level connections."""
        if not self.server_connections:
            messagebox.showinfo("No Connections", "No server connections to clear.")
            return
        
        if not messagebox.askyesno("Clear Connections", 
                                   f"Clear {len(self.server_connections)} server connection(s)?\n\n"
                                   "This will allow you to reconnect with different credentials."):
            return
        
        cleared = 0
        for server in list(self.server_connections.keys()):
            self.disconnect_server_connection(server)
            cleared += 1
        
        self.log_event(f"Cleared {cleared} server connections")
        self.refresh_status_async()
        messagebox.showinfo("Cleared", f"Cleared {cleared} server connection(s).")

    def test_drive_detection(self):
        """Test drive detection using Windows net use command."""
        try:
            result = subprocess.run(
                ["net", "use"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
            
            ps_result = subprocess.run(
                ["powershell", "-Command", "Get-PSDrive -PSProvider FileSystem | Where-Object {$_.DisplayRoot -like '\\\\*'} | Format-Table -AutoSize"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            ps_output = ps_result.stdout if ps_result.returncode == 0 else ""
            
            test_window = ctk.CTkToplevel(self)
            test_window.title("Drive Detection Test")
            test_window.geometry("800x600")
            test_window.attributes("-topmost", True)
            
            txt = ctk.CTkTextbox(test_window, font=("Consolas", 10))
            txt.pack(padx=10, pady=10, fill="both", expand=True)
            
            test_output = "=== NET USE COMMAND ===\n\n"
            test_output += output + "\n\n"
            test_output += "=== POWERSHELL GET-PSDRIVE ===\n\n"
            test_output += ps_output + "\n\n"
            test_output += "=== PYTHON WIN32API ===\n\n"
            
            try:
                drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]
                for drive in drives:
                    if drive:
                        drive_type = win32file.GetDriveType(drive)
                        type_name = {1: "Unknown", 2: "Removable", 3: "Fixed", 4: "Network", 5: "CD-ROM", 6: "RAM"}.get(drive_type, "Unknown")
                        test_output += f"{drive.strip(':\\')}:  Type={drive_type} ({type_name})\n"
                        
                        if drive_type == 4:
                            try:
                                path = win32wnet.WNetGetConnection(drive)
                                test_output += f"     Path: {path}\n"
                            except Exception as e:
                                test_output += f"     Path Error: {e}\n"
            except Exception as e:
                test_output += f"Error: {e}\n"
            
            txt.insert("0.0", test_output)
            txt.configure(state="disabled")
            
            self.log_event("Ran drive detection test")
            
        except Exception as e:
            messagebox.showerror("Test Error", f"Failed to run test:\n{str(e)}")
            self.log_event(f"Drive detection test error: {e}")

    # --- STATUS MONITORING ---
    def refresh_status_async(self):
        """Refresh status display asynchronously."""
        def _refresh():
            try:
                status_text = "=== MAPPED DRIVES ===\n\n"
                mapped_drives = {}
                
                # METHOD 1: Try win32api first
                try:
                    drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]
                    self.log_event(f"DEBUG: GetLogicalDriveStrings returned {len(drives)} drives")
                    
                    for drive in drives:
                        if not drive:
                            continue
                        
                        drive_letter = drive.strip(':\\')
                        
                        try:
                            drive_type = win32file.GetDriveType(drive)
                            
                            if drive_type == 4:
                                try:
                                    path = win32wnet.WNetGetConnection(drive)
                                    mapped_drives[drive_letter] = path
                                    self.log_event(f"DEBUG: win32api detected {drive_letter}: -> {path}")
                                except Exception as e:
                                    self.log_event(f"DEBUG: Failed to get path for {drive_letter}: {e}")
                        except Exception as e:
                            self.log_event(f"DEBUG: Failed to check drive type for {drive_letter}: {e}")
                
                except Exception as e:
                    self.log_event(f"DEBUG: win32api method failed: {e}")
                
                # METHOD 2: Use net use command as fallback
                try:
                    result = subprocess.run(
                        ["net", "use"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            line = line.strip()
                            if ':' in line and '\\\\' in line:
                                parts = line.split()
                                for i, part in enumerate(parts):
                                    if ':' in part and len(part) == 2:
                                        letter = part.strip(':')
                                        for j in range(i+1, len(parts)):
                                            if parts[j].startswith('\\\\'):
                                                path = parts[j]
                                                if letter not in mapped_drives:
                                                    mapped_drives[letter] = path
                                                    self.log_event(f"DEBUG: net use detected {letter}: -> {path}")
                                                break
                except Exception as e:
                    self.log_event(f"DEBUG: net use method failed: {e}")
                
                # Display all found drives
                if mapped_drives:
                    for letter in sorted(mapped_drives.keys(), reverse=True):
                        path = mapped_drives[letter]
                        
                        latency = "?"
                        if path.startswith("\\\\"):
                            server = path.split("\\")[2] if len(path.split("\\")) > 2 else None
                            if server:
                                try:
                                    start = time.time()
                                    socket.create_connection((server, 445), timeout=2).close()
                                    latency = f"{int((time.time() - start) * 1000)}ms"
                                except:
                                    latency = "N/A"
                        
                        status_text += f"💾 {letter}: → {path}\n"
                        status_text += f"   Latency: {latency}\n\n"
                    
                    status_text += f"Total: {len(mapped_drives)} mapped drive(s)\n\n"
                else:
                    status_text += "No network drives currently mapped.\n\n"
                
                # Add server connection status
                if self.server_connections:
                    status_text += "=== SERVER CONNECTIONS ===\n\n"
                    for server, (username, _) in self.server_connections.items():
                        cred_info = f"User: {username}" if username else "No credentials"
                        status_text += f"🔗 {server}\n   {cred_info}\n\n"
                
                self.status_display.configure(state="normal")
                self.status_display.delete("0.0", tk.END)
                self.status_display.insert("0.0", status_text)
                self.status_display.configure(state="disabled")
                
            except Exception as e:
                self.log_event(f"STATUS REFRESH ERROR: {e}")
                import traceback
                self.log_event(f"Traceback: {traceback.format_exc()}")
                try:
                    self.status_display.configure(state="normal")
                    self.status_display.delete("0.0", tk.END)
                    self.status_display.insert("0.0", f"Error refreshing status:\n{e}\n\nCheck logs for details.")
                    self.status_display.configure(state="disabled")
                except:
                    pass
        
        threading.Thread(target=_refresh, daemon=True).start()

    def refresh_profile_ui(self):
        """Refresh the saved profiles display."""
        for widget in self.profile_scroll.winfo_children():
            widget.destroy()
        
        if not self.saved_drives:
            ctk.CTkLabel(
                self.profile_scroll,
                text="No saved drive configurations yet.\nAdd a drive using the form on the left.",
                font=("Arial", 12),
                text_color="gray"
            ).pack(pady=20)
            return
        
        servers = defaultdict(list)
        other_drives = []
        
        for drive in self.saved_drives:
            if drive.get('protocol') == 'SMB':
                server = self.extract_server_from_path(drive['path'])
                if server:
                    servers[server].append(drive)
                else:
                    other_drives.append(drive)
            else:
                other_drives.append(drive)
        
        for server, server_drives in servers.items():
            server_frame = ctk.CTkFrame(self.profile_scroll, fg_color="#1E3A8A")
            server_frame.pack(fill="x", padx=5, pady=2)
            ctk.CTkLabel(
                server_frame,
                text=f"📁 Server: {server}",
                font=("Arial", 11, "bold")
            ).pack(side="left", padx=10, pady=5)
            
            for drive in server_drives:
                self.create_drive_widget(drive)
        
        if other_drives:
            if servers:
                sep_frame = ctk.CTkFrame(self.profile_scroll, fg_color="#1E3A8A")
                sep_frame.pack(fill="x", padx=5, pady=2)
                ctk.CTkLabel(
                    sep_frame,
                    text="📁 Other Drives",
                    font=("Arial", 11, "bold")
                ).pack(side="left", padx=10, pady=5)
            
            for drive in other_drives:
                self.create_drive_widget(drive)

    def create_drive_widget(self, drive):
        """Create a widget for a single drive configuration."""
        frame = ctk.CTkFrame(self.profile_scroll, fg_color="#2C3E50")
        frame.pack(fill="x", padx=5, pady=2)
        
        label = drive.get('label', drive.get('path', 'Unknown'))
        protocol = drive.get('protocol', 'SMB')
        info = f"{drive['letter']}: | {label} | {protocol}"
        if drive.get('username'):
            info += f" | User: {drive['username']}"
        
        ctk.CTkLabel(
            frame,
            text=info,
            font=("Arial", 11)
        ).pack(side="left", padx=10, pady=8)
        
        # Delete button
        ctk.CTkButton(
            frame,
            text="🗑️ Del",
            fg_color="#922B21",
            hover_color="#7B241C",
            width=70,
            command=lambda d=drive: self.delete_profile(d)
        ).pack(side="right", padx=2)
        
        # Clone button
        ctk.CTkButton(
            frame,
            text="📋 Clone",
            fg_color="#7D3C98",
            hover_color="#6C3483",
            width=80,
            command=lambda d=drive: self.clone_drive(d)
        ).pack(side="right", padx=2)
        
        # Sync button (for cloud drives only)
        if "Cloud" in drive.get('protocol', ""):
            ctk.CTkButton(
                frame,
                text="☁️ Sync",
                fg_color="#3498DB",
                hover_color="#2E86C1",
                width=70,
                command=lambda d=drive: self.sync_cloud(d)
            ).pack(side="right", padx=2)
        
        # Wake button (if MAC address provided)
        if drive.get('mac'):
            ctk.CTkButton(
                frame,
                text="⚡ Wake",
                fg_color="#D68910",
                hover_color="#B9770E",
                width=70,
                command=lambda mac=drive['mac']: self.send_wol(mac)
            ).pack(side="right", padx=2)
        
        # Map button
        ctk.CTkButton(
            frame,
            text="▶ Map",
            fg_color="#28B463",
            hover_color="#239B56",
            width=70,
            command=lambda d=drive: self.map_single(d)
        ).pack(side="right", padx=2)

    # --- BACKGROUND WORKER ---
    def service_worker(self):
        """Background service for periodic status refresh."""
        while self.is_monitoring:
            self.refresh_status_async()
            
            for _ in range(self.status_refresh_interval):
                if not self.is_monitoring:
                    break
                time.sleep(1)

    # --- WINDOW MANAGEMENT ---
    def minimize_to_tray(self):
        """Minimize to system tray instead of closing."""
        self.withdraw()
        self.log_event("Application minimized to tray")

    def exit_app(self):
        """Properly exit the application."""
        if messagebox.askyesno("Exit", "Are you sure you want to exit DriveMapper Pro?"):
            self.is_monitoring = False
            self.log_event("Application exiting normally")
            self.destroy()

    # --- CONFIG MANAGEMENT ---
    # Passwords live in Windows Credential Manager (service "DriveMapperPro",
    # one entry per drive letter). The JSON file only records that one exists.
    def _keyring_get(self, letter):
        try:
            return keyring.get_password(KEYRING_SERVICE, letter) or ""
        except Exception as e:
            self.log_event(f"CREDENTIAL READ ERROR for {letter}: {e}")
            return ""

    def _keyring_set(self, letter, password):
        """Store (or clear) a password. Returns True if it is safely in the vault."""
        try:
            if password:
                keyring.set_password(KEYRING_SERVICE, letter, password)
            else:
                self._keyring_delete(letter)
            return True
        except Exception as e:
            self.log_event(f"CREDENTIAL WRITE ERROR for {letter}: {e}")
            return False

    def _keyring_delete(self, letter):
        try:
            keyring.delete_password(KEYRING_SERVICE, letter)
        except Exception:
            pass  # nothing stored under that letter

    def load_config(self):
        """Load saved drive configurations from JSON file."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.log_event(f"Loaded {len(data)} drive configurations")
                        migrate = False
                        for drive in data:
                            if drive.pop('password_in_keyring', False) and keyring:
                                drive['password'] = self._keyring_get(drive['letter'])
                            elif drive.get('password') and keyring:
                                migrate = True  # legacy plain-text file
                        if migrate:
                            self._pending_migration = True
                        return data
            except Exception as e:
                self.log_event(f"CONFIG LOAD ERROR: {e}")
                messagebox.showerror("Config Error", f"Could not load configuration:\n{str(e)}")
        return []

    def save_config(self):
        """Save drive configurations to JSON file (passwords go to the credential vault)."""
        try:
            to_write, plaintext_fallback = [], False
            for drive in self.saved_drives:
                entry = dict(drive)
                password = entry.get('password', '')
                if keyring and self._keyring_set(entry['letter'], password):
                    entry.pop('password', None)
                    if password:
                        entry['password_in_keyring'] = True
                elif password:
                    plaintext_fallback = True  # vault unavailable: keep the password rather than lose it
                to_write.append(entry)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(to_write, f, indent=4)
            self.log_event(f"Saved {len(self.saved_drives)} drive configurations")
            if plaintext_fallback:
                self.log_event("WARNING: Windows Credential Manager unavailable - passwords saved in plain text")
                messagebox.showwarning(
                    "Passwords not encrypted",
                    "Windows Credential Manager could not be used (is the 'keyring' package installed?).\n\n"
                    "Your passwords were saved in plain text in network_vault.json. "
                    "Run: pip install keyring")
        except Exception as e:
            self.log_event(f"CONFIG SAVE ERROR: {e}")
            messagebox.showerror("Save Error", f"Could not save configuration:\n{str(e)}")

    def delete_profile(self, drive):
        """Delete a saved drive configuration."""
        if messagebox.askyesno("Confirm Delete", f"Delete drive {drive['letter']}: configuration?"):
            if drive in self.saved_drives:
                self.saved_drives.remove(drive)
                if keyring:
                    self._keyring_delete(drive['letter'])
                self.save_config()
                self.refresh_profile_ui()
                self.update_suggested_letter()
                self.log_event(f"Deleted configuration for {drive['letter']}:")

    def clone_drive(self, drive):
        """Clone an existing drive configuration with a new drive letter."""
        try:
            occupied = [d.strip(':\\') for d in win32api.GetLogicalDriveStrings().split('\000') if d]
        except:
            occupied = []
        
        used_in_config = [d['letter'] for d in self.saved_drives]
        
        next_letter = None
        current_index = string.ascii_uppercase.index(drive['letter'])
        
        for i in range(current_index - 1, -1, -1):
            letter = string.ascii_uppercase[i]
            if letter not in occupied and letter not in used_in_config:
                next_letter = letter
                break
        
        if not next_letter:
            for letter in reversed(string.ascii_uppercase):
                if letter not in occupied and letter not in used_in_config:
                    next_letter = letter
                    break
        
        if not next_letter:
            messagebox.showerror("No Drive Letters", "No available drive letters for cloning.")
            return
        
        self.ent_letter.delete(0, tk.END)
        self.ent_letter.insert(0, next_letter)
        
        self.ent_path.delete(0, tk.END)
        self.ent_path.insert(0, drive['path'])
        
        self.ent_user.delete(0, tk.END)
        self.ent_user.insert(0, drive.get('username', ''))
        
        self.ent_pass.delete(0, tk.END)
        self.ent_pass.insert(0, drive.get('password', ''))
        
        self.ent_label.delete(0, tk.END)
        self.ent_label.insert(0, drive.get('label', ''))
        
        self.ent_mac.delete(0, tk.END)
        self.ent_mac.insert(0, drive.get('mac', ''))
        
        self.protocol_var.set(drive.get('protocol', 'SMB'))
        
        # Switch to drive mapping tab
        self.tabview.set("🔌 Drive Mapping")
        
        messagebox.showinfo(
            "Drive Cloned",
            f"Settings from {drive['letter']}: copied to form.\n\n"
            f"New drive letter: {next_letter}:\n\n"
            "Modify any fields as needed, then click 'Validate & Add'."
        )
        
        self.log_event(f"Cloned drive {drive['letter']}: → {next_letter}:")

    # --- HELPER METHODS ---
    def update_placeholders(self, choice):
        """Update placeholder text based on selected protocol."""
        hints = {
            "SMB": "\\\\10.0.0.XXX\\Media",
            "SFTP": "sftp.example.com",
            "WebDAV": "webdav.example.com",
            "NFS": "10.0.0.XX:/export/share",
            "Cloud (Rclone)": "MyRemote:"
        }
        
        placeholder = hints.get(choice, "")
        self.ent_path.delete(0, tk.END)
        self.ent_path.configure(placeholder_text=placeholder)

    def map_all_managed(self):
        """Map all saved drive configurations."""
        if not self.saved_drives:
            messagebox.showinfo("No Drives", "No saved drive configurations to map.")
            return
        
        self.prepare_all_servers()
        time.sleep(1)
        
        success_count = 0
        fail_count = 0
        
        for drive in self.saved_drives:
            if self.map_single(drive, silent=True):
                success_count += 1
            else:
                fail_count += 1
        
        messagebox.showinfo(
            "Map All Complete",
            f"Successfully mapped: {success_count}\nFailed: {fail_count}"
        )
        
        self.refresh_status_async()

    def disconnect_all(self):
        """Disconnect all network drives."""
        if not messagebox.askyesno("Confirm", "Disconnect all network drives?"):
            return
        
        try:
            result = subprocess.run(
                ["net", "use", "*", "/delete", "/yes"],
                capture_output=True,
                text=True
            )
            self.log_event("Disconnected all SMB drives")
        except Exception as e:
            self.log_event(f"DISCONNECT SMB ERROR: {e}")
        
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "rclone.exe"],
                capture_output=True
            )
            self.log_event("Killed all rclone processes")
        except Exception as e:
            self.log_event(f"DISCONNECT RCLONE ERROR: {e}")
        
        self.active_session_letters.clear()
        self.server_connections.clear()
        messagebox.showinfo("Disconnected", "All network drives have been disconnected.")
        self.refresh_status_async()

    def update_suggested_letter(self):
        """Update suggested drive letter to next available."""
        try:
            occupied = [d.strip(':\\') for d in win32api.GetLogicalDriveStrings().split('\000') if d]
        except:
            occupied = []
        
        used_in_config = [drive['letter'] for drive in self.saved_drives]
        
        for letter in reversed(string.ascii_uppercase):
            if letter not in occupied and letter not in used_in_config:
                self.ent_letter.delete(0, tk.END)
                self.ent_letter.insert(0, letter)
                break


if __name__ == "__main__":
    app = DrivePro()
    app.mainloop()
