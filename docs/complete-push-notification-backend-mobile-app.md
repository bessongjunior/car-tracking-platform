# CarTracker — Complete Push Notification Setup
**Firebase Cloud Messaging (FCM) · Backend + Flutter App**
Tief Technologies Ltd

---

## Table of Contents

1. [How notifications flow in CarTracker](#1-how-notifications-flow-in-cartracker)
2. [What triggers a notification](#2-what-triggers-a-notification)
3. [Step 1 — Firebase project prerequisites](#3-step-1--firebase-project-prerequisites)
4. [Step 2 — Backend: Admin SDK credentials](#4-step-2--backend-admin-sdk-credentials)
5. [Step 3 — Android app registration](#5-step-3--android-app-registration)
6. [Step 4 — iOS app registration](#6-step-4--ios-app-registration)
7. [Step 5 — APNs key (iOS only)](#7-step-5--apns-key-ios-only)
8. [Step 6 — Flutter app: notification service](#8-step-6--flutter-app-notification-service)
9. [Step 7 — Android notification channels](#9-step-7--android-notification-channels)
10. [Step 8 — iOS permissions (Info.plist)](#10-step-8--ios-permissions-infoplist)
11. [Step 9 — FCM token registration with the backend](#11-step-9--fcm-token-registration-with-the-backend)
12. [Step 10 — Deep-link navigation on notification tap](#12-step-10--deep-link-navigation-on-notification-tap)
13. [Step 11 — End-to-end test](#13-step-11--end-to-end-test)
14. [Notification payload reference](#14-notification-payload-reference)
15. [Troubleshooting checklist](#15-troubleshooting-checklist)

---

## 1. How notifications flow in CarTracker

```
GPS Device
    │  POST /api/v1/telemetry  (X-Device-Key header)
    ▼
Flask Backend
    ├── Persists Telemetry row (PostgreSQL)
    ├── Pushes GPS to Firebase RTDB  (/vehicles/{id}/gps)
    ├── Runs geofence check  ──► geofence breach → Alert row
    └── Runs speed check     ──► speed exceeded  → Alert row
                                         │
                                         ▼
                                  AlertService.create()
                                         │
                                         ▼
                                  FCMService.notify_org()
                                         │
                           firebase_admin.messaging
                           .send_each_for_multicast()
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
             Android device                            iOS device
          (fleet_alerts channel)                  (APNs → sound + badge)
```

The Flutter app also registers its FCM token with the backend immediately after
OTP verification so the backend always knows which device to reach.

---

## 2. What triggers a notification

| Event | alert_type | Severity | Channel |
|---|---|---|---|
| Vehicle exits / enters a geofence | `geofence` | medium | `fleet_alerts` |
| Vehicle exceeds a zone speed limit | `speed` | high | `fleet_alerts` |
| Driver presses the SOS button | `sos` | critical | `sos_alerts` |
| Vehicle goes offline (heartbeat lost) | `offline` | high | `fleet_alerts` |

All four events are handled in `backend/api/services/services.py` →
`AlertService.create()` → `FCMService.notify_org()`.

---

## 3. Step 1 — Firebase project prerequisites

These must be done **once** in the Firebase Console for the
`emma-smart-traffic` project.

### 3.1 Enable Cloud Messaging

Cloud Messaging is automatically enabled for every Firebase project.
Verify it is active:

1. Open [Firebase Console → emma-smart-traffic](https://console.firebase.google.com/project/emma-smart-traffic)
2. Left sidebar → **Build → Cloud Messaging**
3. If you see "Get started", click it — otherwise it is already active.

### 3.2 Confirm the project number

The **sender ID** (project number) is needed for Android and is already set
in the Flutter app:

```
Project number: 646204188304
```

Location: Firebase Console → Project settings → General → **Project number**.

---

## 4. Step 2 — Backend: Admin SDK credentials

The backend uses the Firebase Admin SDK to call FCM's multicast API.
It needs a service-account private key.

### 4.1 Download the key

1. Firebase Console → **Project settings → Service accounts**
2. Confirm **Firebase Admin SDK** tab is selected
3. Click **Generate new private key** → confirm the warning → file downloads
   (e.g. `emma-smart-traffic-firebase-adminsdk-xxxxx.json`)
4. Rename it:
   ```
   mv ~/Downloads/emma-smart-traffic-firebase-adminsdk-*.json \
      /path/to/car-tracking-platform/backend/serviceAccountKey.json
   ```

### 4.2 Confirm `.env` values

Open `backend/.env` and make sure these two lines are correct:

```env
FIREBASE_CREDENTIALS=serviceAccountKey.json
FIREBASE_DATABASE_URL=https://emma-smart-traffic-default-rtdb.firebaseio.com
```

> `serviceAccountKey.json` is listed in `.gitignore` — never commit it.

### 4.3 Verify the SDK starts

```bash
cd backend
source venv/bin/activate
python run.py
```

Look for this line in the startup log:

```
INFO  api  Firebase Admin SDK initialised
```

If you see `Firebase credentials file not found` instead, double-check the
file location (it must be inside `backend/`, next to `run.py`).

---

## 5. Step 3 — Android app registration

The CarTracker Android app (`com.tieftechnologiesltd.car_tracker`) must be
registered in the Firebase project to receive FCM messages.

### 5.1 Register the app

1. Firebase Console → **Project settings → General → Your apps**
2. Click **Add app** → choose **Android**
3. Fill in:
   - **Android package name:** `com.tieftechnologiesltd.car_tracker`
   - **App nickname:** CarTracker Android
   - **Debug signing certificate SHA-1:** *(optional for FCM; required only for
     Dynamic Links or Phone Auth)*
4. Click **Register app**

### 5.2 Download and replace google-services.json

5. Download `google-services.json` from the wizard
6. Replace the existing file:
   ```
   car_tracker/android/app/google-services.json
   ```
7. Copy the **App ID** shown (format: `1:646204188304:android:xxxxxxxxxxxx`)

### 5.3 Update firebase_options.dart

Open `car_tracker/lib/firebase_options.dart` and replace the placeholder:

```dart
// Before
appId: '1:646204188304:android:cartracker_replace_after_register',

// After — use the real App ID from step 5.2
appId: '1:646204188304:android:YOUR_REAL_APP_ID_HERE',
```

### 5.4 Verify google-services.json content

The file must contain a `client` entry with your package name:

```json
{
  "client": [
    {
      "client_info": {
        "android_client_info": {
          "package_name": "com.tieftechnologiesltd.car_tracker"
        }
      }
    }
  ]
}
```

---

## 6. Step 4 — iOS app registration

Skip this section if you are only targeting Android.

### 6.1 Register the iOS app

1. Firebase Console → **Project settings → Your apps → Add app → iOS**
2. Fill in:
   - **iOS bundle ID:** `com.tieftechnologiesltd.carTracker`
   - **App nickname:** CarTracker iOS
3. Click **Register app**
4. Download **`GoogleService-Info.plist`**

### 6.2 Add the plist to Xcode

1. Open `car_tracker/ios/Runner.xcworkspace` in Xcode
2. Drag `GoogleService-Info.plist` into the **Runner** group
3. In the dialog: check **Copy items if needed** + target **Runner** → Add
4. Update `firebase_options.dart` iOS section:
   ```dart
   appId: '1:646204188304:ios:YOUR_REAL_IOS_APP_ID_HERE',
   ```

---

## 7. Step 5 — APNs key (iOS only)

FCM uses APNs (Apple Push Notification service) to deliver notifications on
iOS. You need an APNs authentication key from Apple.

### 7.1 Create an APNs key

1. Open [Apple Developer → Certificates, Identifiers & Profiles → Keys](https://developer.apple.com/account/resources/authkeys/list)
2. Click **+** to create a new key
3. Name it `CarTracker FCM`
4. Check **Apple Push Notifications service (APNs)**
5. Click **Continue → Register**
6. **Download** the `.p8` file — you can only download it once
7. Note the **Key ID** (10-character alphanumeric string)
8. Note your **Team ID** (found in Membership section of Apple Developer account)

### 7.2 Upload the key to Firebase

1. Firebase Console → **Project settings → Cloud Messaging**
2. Scroll to **Apple app configuration**
3. Under your iOS app, click **Upload** for the APNs Authentication Key
4. Provide:
   - The `.p8` file
   - **Key ID** (from step 7.1)
   - **Team ID** (from step 7.1)
5. Click **Upload**

---

## 8. Step 6 — Flutter app: notification service

The notification service is already implemented at:

```
car_tracker/lib/core/services/notification_service.dart
```

It handles all three delivery states:

| State | Handler | What it does |
|---|---|---|
| **Foreground** | `FirebaseMessaging.onMessage` | Shows a local notification via `flutter_local_notifications` |
| **Background** | `FirebaseMessaging.onBackgroundMessage` | `_firebaseBackgroundHandler` top-level function — runs in an isolate |
| **Terminated** | `getInitialMessage()` | Called on cold start when the user tapped the notification |

### 8.1 Verify pubspec.yaml dependencies

These must all be present in `car_tracker/pubspec.yaml`:

```yaml
dependencies:
  firebase_core: ^3.6.0
  firebase_messaging: ^15.1.3
  flutter_local_notifications: ^18.0.1
```

Run `flutter pub get` if you add or change versions.

### 8.2 Verify main.dart initialises Firebase before runApp

```dart
// car_tracker/lib/main.dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
    await NotificationService.init();   // registers FCM handlers
  } catch (e) {
    debugPrint('Firebase not configured: $e');
  }
  await dotenv.load(fileName: '.env');
  runApp(const CarTrackerApp());
}
```

### 8.3 Request permission (iOS + Android 13+)

`NotificationService.init()` must call:

```dart
await FirebaseMessaging.instance.requestPermission(
  alert: true,
  badge: true,
  sound: true,
);
```

On Android 13+ (API 33) you also need the manifest permission (already added):

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
```

Add it above the `<application>` tag if not present.

---

## 9. Step 7 — Android notification channels

FCM messages on Android 8+ must target a notification channel.
Two channels are used in CarTracker, both declared at app startup.

### 9.1 Channel definitions

| Channel ID | Name | Importance | Used for |
|---|---|---|---|
| `fleet_alerts` | Fleet Alerts | High (heads-up) | Geofence, speed, offline |
| `sos_alerts` | SOS Alerts | Max (urgent) | SOS button events |

### 9.2 Create channels in NotificationService.init()

```dart
const fleetChannel = AndroidNotificationChannel(
  'fleet_alerts',
  'Fleet Alerts',
  description: 'Geofence breaches, speed violations, vehicle offline events.',
  importance: Importance.high,
);

const sosChannel = AndroidNotificationChannel(
  'sos_alerts',
  'SOS Alerts',
  description: 'Emergency SOS alerts from drivers.',
  importance: Importance.max,
  playSound: true,
);

final plugin = FlutterLocalNotificationsPlugin();
await plugin
    .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>()
    ?.createNotificationChannel(fleetChannel);

await plugin
    .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>()
    ?.createNotificationChannel(sosChannel);
```

### 9.3 Default channel in AndroidManifest.xml

The manifest already declares the default channel for FCM data messages:

```xml
<meta-data
    android:name="com.google.firebase.messaging.default_notification_channel_id"
    android:value="fleet_alerts" />
```

---

## 10. Step 8 — iOS permissions (Info.plist)

Add the following keys to `car_tracker/ios/Runner/Info.plist` if not present:

```xml
<!-- Request permission reason shown to user -->
<key>NSUserNotificationsUsageDescription</key>
<string>CarTracker sends alerts for geofence breaches, speed violations, and SOS events.</string>

<!-- Allow background fetch for silent push -->
<key>UIBackgroundModes</key>
<array>
    <string>fetch</string>
    <string>remote-notification</string>
</array>
```

In Xcode, also enable:
- **Signing & Capabilities → + Capability → Push Notifications**
- **Signing & Capabilities → + Capability → Background Modes →
  check "Remote notifications"**

---

## 11. Step 9 — FCM token registration with the backend

The FCM token must be sent to the backend so it can target the correct device.
This is handled automatically in `AuthApi.verifyOtp()` immediately after the
JWT is stored:

```dart
// car_tracker/lib/core/services/auth_api.dart
static Future<void> verifyOtp(String userId, String otp) async {
  // ... verify with backend, store JWT ...

  // Register FCM token (best-effort, never blocks login)
  try {
    final fcmToken = await NotificationService.getToken();
    if (fcmToken != null) {
      await _dio.post('/devices/fcm-token', data: {
        'fcm_token': fcmToken,
        'platform': Platform.isAndroid ? 'android' : 'ios',
      });
    }
  } catch (_) {}
}
```

The backend endpoint (`POST /api/v1/devices/fcm-token`) upserts the token into
the `device_fcm_tokens` table keyed on `(user_id, organization_id)`.

### Token refresh

FCM tokens can be rotated by Google. Listen for refreshes and re-register:

```dart
// Add inside NotificationService.init()
FirebaseMessaging.instance.onTokenRefresh.listen((newToken) async {
  // Re-post the new token to the backend if the user is already logged in
  final stored = await SecureStorage.getToken();
  if (stored == null) return;
  try {
    await ApiClient.instance.post('/devices/fcm-token', data: {
      'fcm_token': newToken,
      'platform': Platform.isAndroid ? 'android' : 'ios',
    });
  } catch (_) {}
});
```

---

## 12. Step 10 — Deep-link navigation on notification tap

When a user taps a notification, the app should navigate to the relevant screen.
The `data` payload from the backend carries `type`, `vehicleId`, and `alertId`.

### 12.1 Payload structure sent by FCMService.notify_org()

```json
{
  "notification": {
    "title": "Geofence Breach",
    "body": "GE-1234-21 exited zone \"Accra Central\""
  },
  "data": {
    "type": "geofence",
    "vehicleId": "7",
    "alertId": "15"
  }
}
```

### 12.2 Navigation handler

```dart
// car_tracker/lib/core/services/notification_service.dart

static void _handleMessage(RemoteMessage message) {
  final type = message.data['type'] ?? '';
  final vehicleId = message.data['vehicleId'] ?? '';
  final nav = AppRouterKey.navigatorKey.currentState;
  if (nav == null) return;

  switch (type) {
    case 'geofence':
    case 'speed':
    case 'offline':
      nav.pushNamed('/alerts');
      break;
    case 'sos':
      nav.pushNamed('/alerts');   // show alert center; could also open a modal
      break;
    default:
      if (vehicleId.isNotEmpty) {
        nav.pushNamed('/tracking/$vehicleId');
      }
  }
}
```

Wire this into all three delivery states:

```dart
// Foreground tap — already handled by local notification onDidReceiveNotification
// Background tap
FirebaseMessaging.onMessageOpenedApp.listen(_handleMessage);
// Terminated tap
final initial = await FirebaseMessaging.instance.getInitialMessage();
if (initial != null) _handleMessage(initial);
```

---

## 13. Step 11 — End-to-end test

### 13.1 Confirm the backend can send FCM

Start the backend:
```bash
cd backend && source venv/bin/activate && python run.py
```

Check Firebase Admin SDK status:
```bash
curl http://192.168.1.152:5000/api/v1/firebase/status
# Expected: {"data": {"firebase": "connected", ...}}
```

### 13.2 Seed a GPS point that triggers a geofence alert

First create a geofence zone in the DB (via the API or psql), then:

```bash
curl -X POST http://192.168.1.152:5000/api/v1/firebase/gps/seed \
  -H "Content-Type: application/json" \
  -d '{
    "vehicle_id": "hilux-01",
    "lat": 5.6037,
    "lng": -0.1870,
    "heading": 90,
    "speed": 95,
    "plate": "GE-1234-21"
  }'
```

Then post real telemetry (which runs the full alert pipeline):
```bash
curl -X POST http://192.168.1.152:5000/api/v1/telemetry \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: YOUR_DEVICE_API_KEY" \
  -d '{
    "latitude": 5.6037,
    "longitude": -0.1870,
    "speed": 95,
    "course": 90
  }'
```

### 13.3 Send a test notification directly from Firebase Console

1. Firebase Console → **Engage → Messaging → New campaign → Firebase Notification messages**
2. Notification title: `Test Alert`
3. Notification text: `This is a CarTracker test push.`
4. Target: **Single device** → paste the FCM token from the app log
   (printed by `NotificationService.getToken()` during login)
5. Click **Review → Publish**

The notification should appear on the device within a few seconds.

### 13.4 Check backend logs for FCM delivery

After triggering an alert via telemetry, look for:
```
INFO  api.services  FCM multicast sent to 1 tokens
```

or a warning like:
```
WARNING  api.services  FCM: 1 failures out of 1
```

Failures usually mean the FCM token is stale — re-login the app to refresh it.

---

## 14. Notification payload reference

### Backend → FCM (what `FCMService.notify_org()` sends)

```python
messaging.MulticastMessage(
    notification=messaging.Notification(
        title=title,   # e.g. "Geofence Breach"
        body=body,     # e.g. "GE-1234-21 exited zone Accra Central"
    ),
    data={
        'type':      alert_type,    # geofence | speed | sos | offline
        'vehicleId': str(vehicle.id),
        'alertId':   str(alert.id),
    },
    android=messaging.AndroidConfig(
        priority='high',
        notification=messaging.AndroidNotification(
            channel_id='sos_alerts' if type == 'sos' else 'fleet_alerts',
        ),
    ),
    apns=messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(sound='default', badge=1),
        ),
    ),
    tokens=tokens,   # list of FCM tokens for all org managers
)
```

### Flutter receives

```dart
RemoteMessage {
  notification: RemoteNotification(
    title: 'Geofence Breach',
    body:  'GE-1234-21 exited zone "Accra Central"',
  ),
  data: {
    'type':      'geofence',
    'vehicleId': '7',
    'alertId':   '15',
  },
}
```

---

## 15. Troubleshooting checklist

| Symptom | Likely cause | Fix |
|---|---|---|
| `Firebase Admin SDK initialised` not in logs | `serviceAccountKey.json` missing or path wrong | Place file in `backend/` and check `FIREBASE_CREDENTIALS` in `.env` |
| Notifications received on iOS simulator only | APNs key not uploaded | Complete Step 5 |
| `SMTPAuthenticationError` in email logs | Wrong `GMAIL_APP_PASSWORD` | Generate a new App Password — never use the Google account password |
| FCM token `None` in Flutter | Firebase not fully configured (placeholder appId) | Register the Android app in Firebase Console and replace appId in `firebase_options.dart` |
| `FCM: 1 failures out of 1` in backend logs | Stale FCM token | User must re-login so the app posts a fresh token via `POST /devices/fcm-token` |
| Notification arrives but tapping does nothing | `_handleMessage` not wired to `onMessageOpenedApp` | Add listener in `NotificationService.init()` |
| Notification not shown while app is in foreground | Local notification not displayed | Ensure `FlutterLocalNotificationsPlugin.show()` is called inside `onMessage` handler |
| `google-services.json` does not contain the package name | App not registered in Firebase | Follow Step 3 — register `com.tieftechnologiesltd.car_tracker` |
| Backend sends FCM but no device receives it | All tokens belong to logged-out users | Re-login on the device so a fresh token is registered |

---

## Files changed / involved in push notification flow

```
car-tracking-platform/
├── backend/
│   ├── serviceAccountKey.json          ← download from Firebase (Step 2)
│   ├── .env                            ← FIREBASE_CREDENTIALS, FIREBASE_DATABASE_URL
│   └── api/
│       ├── __init__.py                 ← _init_firebase() on startup
│       ├── models/models.py            ← DeviceFCMToken table
│       ├── routes/routes.py            ← POST /devices/fcm-token
│       └── services/services.py        ← FCMService.notify_org(), AlertService.create()
│
└── car_tracker/
    ├── pubspec.yaml                     ← firebase_messaging, flutter_local_notifications
    ├── .env                             ← GOOGLE_MAPS_API_KEY (Maps only, not FCM)
    ├── android/
    │   ├── app/
    │   │   ├── google-services.json    ← download after registering app (Step 3)
    │   │   └── src/main/
    │   │       └── AndroidManifest.xml ← channel meta-data, INTERNET permission
    │   └── app/build.gradle.kts        ← google-services plugin
    ├── ios/
    │   └── Runner/
    │       ├── GoogleService-Info.plist ← download after registering app (Step 4)
    │       └── Info.plist              ← background modes, notification permission
    └── lib/
        ├── main.dart                   ← Firebase.initializeApp + NotificationService.init
        ├── firebase_options.dart       ← real appId values after registration
        └── core/
            ├── router/app_router.dart  ← AppRouterKey.navigatorKey for deep links
            └── services/
                ├── notification_service.dart  ← FCM handlers, local notifications
                ├── auth_api.dart              ← posts FCM token after OTP verify
                └── secure_storage.dart        ← JWT storage (not FCM-specific)
```
