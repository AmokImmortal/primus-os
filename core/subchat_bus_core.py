import threading
import queue
from typing import Callable, Dict, Any, List


class SubChatBusCore:
    """
    Internal event/message propagation engine.
    Handles:
      - Core event routing
      - Broadcast to all subscribers
      - Channel-specific delivery
      - Thread-safe message queue
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[Any], None]]] = {}  # event_name → [callbacks]
        self.global_subscribers: List[Callable[[str, Any], None]] = []  # receives all events
        self.message_queue = queue.Queue()
        self._running = False
        self._worker_thread = None

    # -------------------------------------------------------------------------
    # Subscription Management
    # -------------------------------------------------------------------------
    def subscribe(self, event_name: str, callback: Callable[[Any], None]):
        """Subscribe a callback to a specific event."""
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []
        self.subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]):
        """Unsubscribe a callback from an event."""
        if event_name in self.subscribers:
            try:
                self.subscribers[event_name].remove(callback)
            except ValueError:
                pass

    def subscribe_global(self, callback: Callable[[str, Any], None]):
        """Subscribe to all events."""
        self.global_subscribers.append(callback)

    # -------------------------------------------------------------------------
    # Event Publishing
    # -------------------------------------------------------------------------
    def publish(self, event_name: str, payload: Any):
        """
        Queue an event for dispatch.
        Thread-safe: producers can be anywhere in the system.
        """
        self.message_queue.put((event_name, payload))

    # -------------------------------------------------------------------------
    # Internal Event Loop
    # -------------------------------------------------------------------------
    def start(self):
        """
        Start the event dispatch worker thread.
        The main PRIMUS runtime will call this during boot.
        """
        if self._running:
            return

        self._running = True
        self._worker_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        """Stop the event loop."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join()

    def _event_loop(self):
        """Continuously consume and dispatch events."""
        while self._running:
            try:
                event_name, payload = self.message_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Notify specific event subscribers
            if event_name in self.subscribers:
                for callback in self.subscribers[event_name]:
                    try:
                        callback(payload)
                    except Exception as e:
                        print(f"[SubChatBusCore] Error in subscriber for {event_name}: {e}")

            # Notify global subscribers
            for callback in self.global_subscribers:
                try:
                    callback(event_name, payload)
                except Exception as e:
                    print(f"[SubChatBusCore] Error in global subscriber: {e}")