#!/usr/bin/env python3
"""
User Interface Components for kSync
Provides command-line interface and status display
"""

from typing import Dict, Any, Callable, Optional


class CommandInterface:
    """Command-line interface for kSync"""

    def __init__(self, app_name: str = "kSync"):
        self.app_name = app_name
        self.commands: Dict[str, Dict[str, Any]] = {}
        self.running = False

    def register_command(self, name: str, handler: Callable, description: str) -> None:
        """Register a command handler"""
        self.commands[name] = {"handler": handler, "description": description}

    def show_help(self) -> None:
        """Display available commands"""
        print(f"\n=== {self.app_name} Control ===")
        print("Commands:")
        for name, info in self.commands.items():
            print(f"  {name:<12} - {info['description']}")
        print("  help         - Show this help message")
        print("  quit         - Exit program")

    def run(self) -> None:
        """Run the command interface"""
        self.running = True
        self.show_help()

        try:
            while self.running:
                try:
                    user_input = input(f"\n{self.app_name.lower()}> ").strip()

                    if not user_input:
                        continue

                    # Split command and arguments
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []

                    if cmd in ["quit", "exit", "q"]:
                        break
                    elif cmd == "help":
                        self.show_help()
                    elif cmd in self.commands:
                        try:
                            # Pass arguments to the handler
                            if args:
                                self.commands[cmd]["handler"](*args)
                            else:
                                self.commands[cmd]["handler"]()
                        except Exception as e:
                            print(f"Error executing command '{cmd}': {e}")
                    else:
                        print("Unknown command. Type 'help' for available commands.")

                except EOFError:
                    break

        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            print(f"\nGoodbye from {self.app_name}!")

    def stop(self) -> None:
        """Stop the command interface"""
        self.running = False


class StatusDisplay:
    """Displays system status information"""

    @staticmethod
    def show_leader_status(
        system_state: Any, collaborators: Dict[str, Dict], schedule_count: int = 0
    ) -> None:
        """Display leader status"""
        print("\n=== kSync Leader Status ===")
        print(f"System running: {system_state.is_running}")

        if system_state.is_running:
            elapsed = system_state.get_elapsed_time()
            print(
                f"Elapsed time: {elapsed:.2f} seconds ({system_state.get_formatted_time()})"
            )

        print(f"\nConnected Collaborators: {len(collaborators)}")
        for device_id, info in collaborators.items():
            status = "ONLINE" if info.get("online", False) else "OFFLINE"
            print(
                f"  {device_id}: {info.get('ip', 'unknown')} - {status}"
            )

    @staticmethod
    def show_collaborator_status(
        device_id: str,
        video_file: str,
        is_running: bool,
        sync_stats: Optional[Dict] = None,
    ) -> None:
        """Display collaborator status"""
        print(f"\n=== kSync Collaborator Status ({device_id}) ===")
        print(f"Video file: {video_file}")
        print(f"Status: {'RUNNING' if is_running else 'READY'}")

        if sync_stats:
            print(f"Average drift: {sync_stats.get('average_drift', 0):.3f}s")


class ProgressDisplay:
    """Displays progress and timing information"""

    def __init__(self, width: int = 50):
        self.width = width
        self.last_display_time = 0

    def show_progress(
        self, current_time: float, total_time: float, additional_info: str = ""
    ) -> None:
        """Show progress bar and timing"""
        import time

        if time.time() - self.last_display_time < 1.0:
            return
        self.last_display_time = time.time()

        if total_time <= 0:
            percent = 0
        else:
            percent = min(100, (current_time / total_time) * 100)

        # Create progress bar
        filled = int((percent / 100) * self.width)
        bar = "█" * filled + "░" * (self.width - filled)

        # Format time
        current_min = int(current_time // 60)
        current_sec = int(current_time % 60)
        total_min = int(total_time // 60)
        total_sec = int(total_time % 60)

        time_str = (
            f"{current_min:02d}:{current_sec:02d}/{total_min:02d}:{total_sec:02d}"
        )

        # Display
        line = f"\r[{bar}] {percent:5.1f}% {time_str}"
        if additional_info:
            line += f" | {additional_info}"

        print(line, end="", flush=True)

    def clear_progress(self) -> None:
        """Clear the progress line"""
        print("\r" + " " * 80 + "\r", end="", flush=True)


class ErrorDisplay:
    """Displays error messages and warnings"""

    @staticmethod
    def show_error(message: str, details: str = "") -> None:
        """Display error message"""
        print(f"ERROR: {message}")
        if details:
            print(f"   Details: {details}")

    @staticmethod
    def show_warning(message: str) -> None:
        """Display warning message"""
        print(f"WARNING: {message}")

    @staticmethod
    def show_info(message: str) -> None:
        """Display info message"""
        print(f"INFO: {message}")

    @staticmethod
    def show_success(message: str) -> None:
        """Display success message"""
        print(f"SUCCESS: {message}")


class MenuInterface:
    """Simple menu-based interface"""

    def __init__(self, title: str):
        self.title = title
        self.options: Dict[str, Dict[str, Any]] = {}

    def add_option(self, key: str, description: str, handler: Callable) -> None:
        """Add a menu option"""
        self.options[key] = {"description": description, "handler": handler}

    def show_menu(self) -> None:
        """Display the menu"""
        print(f"\n=== {self.title} ===")
        for key, info in self.options.items():
            print(f"  {key}. {info['description']}")
        print("  q. Quit/Return")

    def run(self) -> None:
        """Run the menu interface"""
        while True:
            self.show_menu()
            choice = input("\nSelect option: ").strip().lower()

            if choice in ["q", "quit", "exit"]:
                break
            elif choice in self.options:
                try:
                    result = self.options[choice]["handler"]()
                    if result is False:  # Handler can return False to exit
                        break
                except Exception as e:
                    ErrorDisplay.show_error(
                        f"Error executing option '{choice}'", str(e)
                    )
            else:
                print("Invalid option. Please try again.")

        print("Returning to main menu...")
