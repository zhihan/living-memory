import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:intl/intl.dart';

/// Cached device timezone (IANA string).
String? _cachedDeviceTz;

/// Get the device's IANA timezone string, with caching.
Future<String> getDeviceTimezone() async {
  _cachedDeviceTz ??= await FlutterTimezone.getLocalTimezone();
  return _cachedDeviceTz!;
}

/// Check whether two IANA timezone names refer to the same timezone.
///
/// This is a simple string comparison. For most practical purposes it works
/// because the backend and the device both use canonical IANA names.
bool timezonesMatch(String roomTimezone, String deviceTimezone) {
  return roomTimezone == deviceTimezone;
}

/// Format a UTC datetime for display.
///
/// When the user's device timezone matches the room timezone, returns a single
/// formatted string. When they differ, returns a dual format:
///   "Fri, Jan 3, 2026 19:00 (EST) / Sat, Jan 4, 2026 08:00 (CST)"
///
/// Note: Dart's `toLocal()` converts to the device timezone. For the room
/// timezone we'd need a timezone library (e.g. `timezone`). Since most users
/// are in the same timezone as their room, the dual format shows the device
/// local time plus a label noting it differs from the room timezone.
String formatDualDate(
  String isoString,
  String roomTimezone,
  String deviceTimezone, {
  String pattern = 'E, MMM d, yyyy  HH:mm',
}) {
  final dt = DateTime.parse(isoString).toLocal();
  final formatted = DateFormat(pattern).format(dt);

  if (timezonesMatch(roomTimezone, deviceTimezone)) {
    return formatted;
  }

  // Show device-local time with a note about the room timezone
  final deviceAbbr = dt.timeZoneName;
  final roomShort = roomTimezone.split('/').last.replaceAll('_', ' ');
  return '$formatted ($deviceAbbr) · Room: $roomShort';
}
