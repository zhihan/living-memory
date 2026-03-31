class ScheduleRule {
  final String frequency;
  final List<int> weekdays;
  final int interval;
  final String? until;
  final int? count;

  const ScheduleRule({
    required this.frequency,
    this.weekdays = const [],
    this.interval = 1,
    this.until,
    this.count,
  });

  factory ScheduleRule.fromJson(Map<String, dynamic> json) {
    return ScheduleRule(
      frequency: json['frequency'] as String,
      weekdays: List<int>.from(json['weekdays'] ?? []),
      interval: json['interval'] as int? ?? 1,
      until: json['until'] as String?,
      count: json['count'] as int?,
    );
  }

  Map<String, dynamic> toJson() => {
        'frequency': frequency,
        'weekdays': weekdays,
        'interval': interval,
        'until': until,
        'count': count,
      };
}

class Series {
  final String seriesId;
  final String workspaceId;
  final String kind;
  final String title;
  final ScheduleRule scheduleRule;
  final String? defaultTime;
  final int? defaultDurationMinutes;
  final String? defaultLocation;
  final String? defaultOnlineLink;
  final String locationType;
  final List<String>? locationRotation;
  final String status;
  final List<int>? checkInWeekdays;
  final String? description;
  final String? createdBy;
  final String hostRotationMode;
  final List<String>? hostRotation;
  final Map<String, String>? hostAddresses;

  const Series({
    required this.seriesId,
    required this.workspaceId,
    required this.kind,
    required this.title,
    required this.scheduleRule,
    this.defaultTime,
    this.defaultDurationMinutes,
    this.defaultLocation,
    this.defaultOnlineLink,
    this.locationType = 'fixed',
    this.locationRotation,
    this.status = 'active',
    this.checkInWeekdays,
    this.description,
    this.createdBy,
    this.hostRotationMode = 'none',
    this.hostRotation,
    this.hostAddresses,
  });

  factory Series.fromJson(Map<String, dynamic> json) {
    Map<String, String>? addresses;
    final rawAddresses = json['host_addresses'];
    if (rawAddresses is Map) {
      addresses = {};
      rawAddresses.forEach((k, v) {
        addresses![k.toString()] = v as String;
      });
    }

    return Series(
      seriesId: json['series_id'] as String,
      workspaceId: json['workspace_id'] as String,
      kind: json['kind'] as String,
      title: json['title'] as String,
      scheduleRule: ScheduleRule.fromJson(
          json['schedule_rule'] as Map<String, dynamic>),
      defaultTime: json['default_time'] as String?,
      defaultDurationMinutes: json['default_duration_minutes'] as int?,
      defaultLocation: json['default_location'] as String?,
      defaultOnlineLink: json['default_online_link'] as String?,
      locationType: json['location_type'] as String? ?? 'fixed',
      locationRotation: json['location_rotation'] != null
          ? List<String>.from(json['location_rotation'])
          : null,
      status: json['status'] as String? ?? 'active',
      checkInWeekdays: json['check_in_weekdays'] != null
          ? List<int>.from(json['check_in_weekdays'])
          : null,
      description: json['description'] as String?,
      createdBy: json['created_by'] as String?,
      hostRotationMode: json['host_rotation_mode'] as String? ?? 'none',
      hostRotation: json['host_rotation'] != null
          ? List<String>.from(json['host_rotation'])
          : null,
      hostAddresses: addresses,
    );
  }

  String get scheduleDescription {
    final rule = scheduleRule;
    switch (rule.frequency) {
      case 'daily':
        return rule.interval > 1
            ? 'Every ${rule.interval} days'
            : 'Daily';
      case 'weekly':
      case 'custom':
        final days = rule.weekdays.map(_weekdayName).join(', ');
        final prefix = rule.interval > 1
            ? 'Every ${rule.interval} weeks'
            : 'Weekly';
        return days.isEmpty ? prefix : '$prefix on $days';
      case 'weekdays':
        return 'Weekdays (Mon-Fri)';
      case 'once':
        return 'One-time';
      default:
        return rule.frequency;
    }
  }

  static String _weekdayName(int day) {
    const names = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return day >= 1 && day <= 7 ? names[day] : '?';
  }
}
