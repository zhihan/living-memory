class Room {
  final String roomId;
  final String title;
  final String type;
  final String timezone;
  final List<String> ownerUids;
  final Map<String, String> memberRoles;
  final Map<String, Map<String, String?>> memberProfiles;
  final String? description;
  final int seriesCount;
  final Map<String, dynamic>? seriesSchedule;
  final String? seriesDefaultTime;
  final String? myRole;

  const Room({
    required this.roomId,
    required this.title,
    required this.type,
    required this.timezone,
    required this.ownerUids,
    required this.memberRoles,
    required this.memberProfiles,
    this.description,
    this.seriesCount = 0,
    this.seriesSchedule,
    this.seriesDefaultTime,
    this.myRole,
  });

  factory Room.fromJson(Map<String, dynamic> json) {
    final roles = <String, String>{};
    final rawRoles = json['member_roles'];
    if (rawRoles is Map) {
      rawRoles.forEach((k, v) {
        roles[k.toString()] = v as String;
      });
    }
    final profiles = <String, Map<String, String?>>{};
    final rawProfiles = json['member_profiles'];
    if (rawProfiles is Map) {
      rawProfiles.forEach((k, v) {
        final m = <String, String?>{};
        if (v is Map) {
          v.forEach((pk, pv) {
            m[pk.toString()] = pv as String?;
          });
        }
        profiles[k.toString()] = m;
      });
    }
    return Room(
      roomId: json['room_id'] as String,
      title: json['title'] as String,
      type: json['type'] as String? ?? 'shared',
      timezone: json['timezone'] as String? ?? 'UTC',
      ownerUids: List<String>.from(json['owner_uids'] ?? []),
      memberRoles: roles,
      memberProfiles: profiles,
      description: json['description'] as String?,
      seriesCount: json['series_count'] as int? ?? 0,
      seriesSchedule: json['series_schedule'] as Map<String, dynamic>?,
      seriesDefaultTime: json['series_default_time'] as String?,
      myRole: json['my_role'] as String?,
    );
  }

  String get seriesSubtitle {
    if (seriesCount == 0) return 'No series';
    if (seriesCount == 1 && seriesSchedule != null) {
      final freq = seriesSchedule!['frequency'] as String? ?? '';
      String text;
      if (freq == 'daily') {
        text = 'Every day';
      } else if (freq == 'weekdays') {
        text = 'Weekdays (Mon-Fri)';
      } else if (freq == 'weekly') {
        final weekdays = (seriesSchedule!['weekdays'] as List?)?.cast<int>() ?? [];
        if (weekdays.isNotEmpty) {
          const dayMap = {1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat', 7: 'Sun'};
          text = 'Weekly on ${weekdays.map((d) => dayMap[d] ?? '$d').join(', ')}';
        } else {
          text = 'Weekly';
        }
      } else {
        text = freq;
      }
      if (seriesDefaultTime != null) text += ' at $seriesDefaultTime';
      return text;
    }
    return '$seriesCount series';
  }
}

class MemberDetail {
  final String uid;
  final String role;
  final String? displayName;
  final String? email;

  const MemberDetail({
    required this.uid,
    required this.role,
    this.displayName,
    this.email,
  });

  factory MemberDetail.fromJson(Map<String, dynamic> json) {
    return MemberDetail(
      uid: json['uid'] as String,
      role: json['role'] as String,
      displayName: json['display_name'] as String?,
      email: json['email'] as String?,
    );
  }
}
