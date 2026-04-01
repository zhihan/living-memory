class OccurrenceOverrides {
  final String? time;
  final int? durationMinutes;
  final String? location;
  final String? onlineLink;
  final String? title;
  final String? notes;

  const OccurrenceOverrides({
    this.time,
    this.durationMinutes,
    this.location,
    this.onlineLink,
    this.title,
    this.notes,
  });

  factory OccurrenceOverrides.fromJson(Map<String, dynamic> json) {
    return OccurrenceOverrides(
      time: json['time'] as String?,
      durationMinutes: json['duration_minutes'] as int?,
      location: json['location'] as String?,
      onlineLink: json['online_link'] as String?,
      title: json['title'] as String?,
      notes: json['notes'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        if (time != null) 'time': time,
        if (durationMinutes != null) 'duration_minutes': durationMinutes,
        if (location != null) 'location': location,
        if (onlineLink != null) 'online_link': onlineLink,
        if (title != null) 'title': title,
        if (notes != null) 'notes': notes,
      };
}

class Occurrence {
  final String occurrenceId;
  final String seriesId;
  final String roomId;
  final String scheduledFor;
  final String status;
  final String? location;
  final OccurrenceOverrides? overrides;
  final int? sequenceIndex;
  final bool enableCheckIn;
  final String? host;
  final String? prevOccurrenceId;
  final String? nextOccurrenceId;

  const Occurrence({
    required this.occurrenceId,
    required this.seriesId,
    required this.roomId,
    required this.scheduledFor,
    this.status = 'scheduled',
    this.location,
    this.overrides,
    this.sequenceIndex,
    this.enableCheckIn = false,
    this.host,
    this.prevOccurrenceId,
    this.nextOccurrenceId,
  });

  factory Occurrence.fromJson(Map<String, dynamic> json) {
    return Occurrence(
      occurrenceId: json['occurrence_id'] as String,
      seriesId: json['series_id'] as String,
      roomId: json['room_id'] as String,
      scheduledFor: json['scheduled_for'] as String,
      status: json['status'] as String? ?? 'scheduled',
      location: json['location'] as String?,
      overrides: json['overrides'] != null
          ? OccurrenceOverrides.fromJson(
              json['overrides'] as Map<String, dynamic>)
          : null,
      sequenceIndex: json['sequence_index'] as int?,
      enableCheckIn: json['enable_check_in'] as bool? ?? false,
      host: json['host'] as String?,
      prevOccurrenceId: json['prev_occurrence_id'] as String?,
      nextOccurrenceId: json['next_occurrence_id'] as String?,
    );
  }

  String get effectiveTitle => overrides?.title ?? '';
  String? get effectiveLocation => overrides?.location ?? location;
  String? get effectiveOnlineLink => overrides?.onlineLink;
  String? get effectiveNotes => overrides?.notes;

  DateTime get scheduledDateTime => DateTime.parse(scheduledFor);
}
