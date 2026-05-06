/**
 * Realtime sync singleton: a thin wrapper around socket.io-client that
 * auto-connects when a token is available, joins each space room, and lets
 * components subscribe to space.event / user.event broadcasts.
 *
 * Backend mounts socket.io at /api/socket.io and broadcasts to:
 *   - room "space:<space_id>"  → space.event { kind, action, payload }
 *   - room "user:<user_id>"    → user.event  { kind, action, payload }
 */
import { io, Socket } from 'socket.io-client';
import { tokenStorage, BASE_URL } from './api';

export type SpaceEvent = {
  space_id: string;
  kind: string;
  action: string;
  payload: any;
  ts?: string;
};

export type UserEvent = {
  user_id: string;
  kind: string;
  action: string;
  payload: any;
  ts?: string;
};

type SpaceCb = (e: SpaceEvent) => void;
type UserCb = (e: UserEvent) => void;
type StatusCb = (connected: boolean) => void;

class RealtimeClient {
  private socket: Socket | null = null;
  private spaceListeners: Set<SpaceCb> = new Set();
  private userListeners: Set<UserCb> = new Set();
  private statusListeners: Set<StatusCb> = new Set();
  private connected = false;
  private currentToken: string | null = null;

  /** Connect (or reconnect if token changed). Idempotent. */
  async connect(): Promise<void> {
    const token = await tokenStorage.get();
    if (!token) {
      this.disconnect();
      return;
    }
    if (this.socket && this.currentToken === token && this.socket.connected) return;
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
    this.currentToken = token;
    const url = (BASE_URL || '').replace(/\/api\/?$/, ''); // strip trailing /api if BASE_URL ends with it
    const s = io(url, {
      path: '/api/socket.io',
      transports: ['websocket', 'polling'],
      auth: { token },
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    });
    s.on('connect', () => {
      this.connected = true;
      this.statusListeners.forEach((cb) => { try { cb(true); } catch {} });
    });
    s.on('disconnect', () => {
      this.connected = false;
      this.statusListeners.forEach((cb) => { try { cb(false); } catch {} });
    });
    s.on('connect_error', (err) => {
      // 401-like reject: stop retrying with this token
      if (String(err?.message || '').toLowerCase().includes('unauthorized')) {
        s.disconnect();
      }
    });
    s.on('space.event', (e: SpaceEvent) => {
      this.spaceListeners.forEach((cb) => { try { cb(e); } catch {} });
    });
    s.on('user.event', (e: UserEvent) => {
      this.userListeners.forEach((cb) => { try { cb(e); } catch {} });
    });
    s.on('hello', () => { /* server handshake, rooms auto-joined backend-side */ });
    this.socket = s;
  }

  joinSpace(spaceId: string) {
    if (!this.socket || !this.socket.connected || !spaceId) return;
    try {
      this.socket.emit('join_room', { space_id: spaceId });
    } catch {}
  }

  disconnect() {
    if (this.socket) {
      try { this.socket.disconnect(); } catch {}
      this.socket = null;
    }
    this.currentToken = null;
    this.connected = false;
    this.statusListeners.forEach((cb) => { try { cb(false); } catch {} });
  }

  isConnected() { return this.connected; }

  onSpaceEvent(cb: SpaceCb) { this.spaceListeners.add(cb); return () => this.spaceListeners.delete(cb); }
  onUserEvent(cb: UserCb) { this.userListeners.add(cb); return () => this.userListeners.delete(cb); }
  onStatus(cb: StatusCb) { this.statusListeners.add(cb); return () => this.statusListeners.delete(cb); }
}

export const realtime = new RealtimeClient();
