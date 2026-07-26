/**
 * Turning on alerts.
 *
 * The whole proactive design rests on this one permission. If it is not granted
 * the app is a thing someone has to remember to open, on the evening they are
 * least likely to think of it.
 *
 * Two platform facts shape the flow:
 *   - iOS only allows push once the app is on the home screen, so an iPhone user
 *     who has not installed it needs different words, not a failed prompt.
 *   - Browsers permanently block a site that asks and is refused, so the prompt
 *     is only ever raised from a deliberate tap.
 */

export type PushState =
  | 'unsupported'
  | 'needs-install'
  | 'prompt'
  | 'granted'
  | 'denied'

export type Audience = 'caregiver' | 'cared_for'

export interface PushIdentity {
  personId: string
  audience: Audience
}

export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS predates display-mode and reports installation here instead.
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  )
}

export function isIos(): boolean {
  if (typeof navigator === 'undefined') return false
  return /iPad|iPhone|iPod/.test(navigator.userAgent)
}

export function pushState(): PushState {
  if (typeof window === 'undefined') return 'unsupported'
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    // On iOS this is not a dead end — installing to the home screen makes the
    // same browser capable, so say that rather than "unsupported".
    return isIos() && !isStandalone() ? 'needs-install' : 'unsupported'
  }
  if (Notification.permission === 'granted') return 'granted'
  if (Notification.permission === 'denied') return 'denied'
  return 'prompt'
}

/**
 * The state including whether a subscription actually exists.
 *
 * `pushState` alone reads only the browser permission, and permission survives
 * `unsubscribe()`. So after someone turns alerts off, a reload would show
 * "Alerts are on" while nothing is registered and no alert could ever arrive —
 * the screen telling a caregiver they are covered when they are not.
 */
export async function currentPushState(): Promise<PushState> {
  const state = pushState()
  if (state !== 'granted') return state

  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  return subscription ? 'granted' : 'prompt'
}

/**
 * Base64url from the environment to the bytes the Push API wants.
 *
 * Backed by an explicit ArrayBuffer rather than `Uint8Array.from`, because
 * `applicationServerKey` will not accept a view that might sit on a
 * SharedArrayBuffer.
 */
function decodeKey(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4))
    .replace(/-/g, '+')
    .replace(/_/g, '/')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  return bytes
}

export async function enablePush(identity: PushIdentity): Promise<PushState> {
  const state = pushState()
  if (state !== 'prompt' && state !== 'granted') return state

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'prompt'

  const key = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY
  if (!key) throw new Error('NEXT_PUBLIC_VAPID_PUBLIC_KEY is not set')

  const registration = await navigator.serviceWorker.ready
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      // Chrome refuses silent pushes outright, and a safety alert that shows
      // nothing would be worse than one that never arrived.
      userVisibleOnly: true,
      applicationServerKey: decodeKey(key),
    }))

  const response = await fetch('/api/push/subscribe', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ subscription: subscription.toJSON(), ...identity }),
  })
  if (!response.ok) throw new Error(`could not register for alerts (${response.status})`)

  return 'granted'
}

export async function disablePush(): Promise<void> {
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) return

  await fetch('/api/push/subscribe', {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ endpoint: subscription.endpoint }),
  })
  await subscription.unsubscribe()
}
