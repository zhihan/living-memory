import 'package:intl/intl.dart';
import 'timezone_helpers.dart';

String formatOccurrenceDate(String isoString, {String? roomTimezone, String? deviceTimezone}) {
  final dt = DateTime.parse(isoString).toLocal();
  final formatted = DateFormat('E, MMM d, yyyy  HH:mm').format(dt);

  if (roomTimezone == null || deviceTimezone == null ||
      timezonesMatch(roomTimezone, deviceTimezone)) {
    return formatted;
  }

  final deviceAbbr = dt.timeZoneName;
  final roomShort = roomTimezone.split('/').last.replaceAll('_', ' ');
  return '$formatted ($deviceAbbr) · Room: $roomShort';
}

String formatShortDate(String isoString) {
  final dt = DateTime.parse(isoString).toLocal();
  return DateFormat('M/d').format(dt);
}
