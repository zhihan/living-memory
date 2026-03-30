import 'package:intl/intl.dart';

String formatOccurrenceDate(String isoString) {
  final dt = DateTime.parse(isoString).toLocal();
  return DateFormat('E, MMM d, yyyy  HH:mm').format(dt);
}

String formatShortDate(String isoString) {
  final dt = DateTime.parse(isoString).toLocal();
  return DateFormat('M/d').format(dt);
}
