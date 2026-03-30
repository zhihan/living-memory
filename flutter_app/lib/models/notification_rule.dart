class NotificationRule {
  final String ruleId;
  final String workspaceId;
  final String? seriesId;
  final String channel;
  final int remindBeforeMinutes;
  final bool enabled;
  final List<String> targetRoles;

  const NotificationRule({
    required this.ruleId,
    required this.workspaceId,
    this.seriesId,
    required this.channel,
    required this.remindBeforeMinutes,
    this.enabled = true,
    this.targetRoles = const [],
  });

  factory NotificationRule.fromJson(Map<String, dynamic> json) {
    return NotificationRule(
      ruleId: json['rule_id'] as String,
      workspaceId: json['workspace_id'] as String,
      seriesId: json['series_id'] as String?,
      channel: json['channel'] as String,
      remindBeforeMinutes: json['remind_before_minutes'] as int,
      enabled: json['enabled'] as bool? ?? true,
      targetRoles: List<String>.from(json['target_roles'] ?? []),
    );
  }
}
