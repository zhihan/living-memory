class CheckIn {
  final String checkInId;
  final String occurrenceId;
  final String seriesId;
  final String workspaceId;
  final String userId;
  final String? displayName;
  final String status;
  final String? checkedInAt;
  final String? note;

  const CheckIn({
    required this.checkInId,
    required this.occurrenceId,
    required this.seriesId,
    required this.workspaceId,
    required this.userId,
    this.displayName,
    this.status = 'pending',
    this.checkedInAt,
    this.note,
  });

  factory CheckIn.fromJson(Map<String, dynamic> json) {
    return CheckIn(
      checkInId: json['check_in_id'] as String,
      occurrenceId: json['occurrence_id'] as String,
      seriesId: json['series_id'] as String,
      workspaceId: json['workspace_id'] as String,
      userId: json['user_id'] as String,
      displayName: json['display_name'] as String?,
      status: json['status'] as String? ?? 'pending',
      checkedInAt: json['checked_in_at'] as String?,
      note: json['note'] as String?,
    );
  }
}
