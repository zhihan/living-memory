import 'package:test/test.dart';
import 'package:event_ledger/models/series.dart';

void main() {
  group('ScheduleRule', () {
    test('fromJson parses weekly rule', () {
      final json = {
        'frequency': 'weekly',
        'weekdays': [1, 3, 5],
        'interval': 1,
      };
      final rule = ScheduleRule.fromJson(json);
      expect(rule.frequency, 'weekly');
      expect(rule.weekdays, [1, 3, 5]);
      expect(rule.interval, 1);
      expect(rule.until, isNull);
      expect(rule.count, isNull);
    });

    test('toJson round-trips', () {
      final rule = ScheduleRule(
        frequency: 'daily',
        weekdays: [],
        interval: 2,
        count: 10,
      );
      final json = rule.toJson();
      expect(json['frequency'], 'daily');
      expect(json['interval'], 2);
      expect(json['count'], 10);

      final roundTripped = ScheduleRule.fromJson(json);
      expect(roundTripped.frequency, rule.frequency);
      expect(roundTripped.interval, rule.interval);
      expect(roundTripped.count, rule.count);
    });
  });

  group('Series', () {
    test('fromJson parses full series', () {
      final json = {
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'kind': 'meeting',
        'title': 'Weekly Standup',
        'schedule_rule': {
          'frequency': 'weekly',
          'weekdays': [1, 2, 3, 4, 5],
          'interval': 1,
        },
        'default_time': '09:00',
        'default_duration_minutes': 30,
        'default_location': 'Room A',
        'default_online_link': 'https://meet.example.com/abc',
        'location_type': 'fixed',
        'status': 'active',
        'check_in_weekdays': [1, 3, 5],
        'description': 'Daily standup meeting',
        'created_by': 'uid-1',
      };
      final series = Series.fromJson(json);
      expect(series.seriesId, 's-1');
      expect(series.title, 'Weekly Standup');
      expect(series.scheduleRule.frequency, 'weekly');
      expect(series.scheduleRule.weekdays, [1, 2, 3, 4, 5]);
      expect(series.defaultTime, '09:00');
      expect(series.defaultDurationMinutes, 30);
      expect(series.defaultLocation, 'Room A');
      expect(series.locationType, 'fixed');
      expect(series.checkInWeekdays, [1, 3, 5]);
    });

    test('scheduleDescription for weekly', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(
          frequency: 'weekly',
          weekdays: [1, 3, 5],
        ),
      );
      expect(series.scheduleDescription, 'Weekly on Mon, Wed, Fri');
    });

    test('scheduleDescription for daily', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(frequency: 'daily'),
      );
      expect(series.scheduleDescription, 'Daily');
    });

    test('scheduleDescription for daily with interval', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(frequency: 'daily', interval: 3),
      );
      expect(series.scheduleDescription, 'Every 3 days');
    });

    test('scheduleDescription for weekdays', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(frequency: 'weekdays'),
      );
      expect(series.scheduleDescription, 'Weekdays (Mon-Fri)');
    });

    test('scheduleDescription for once', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(frequency: 'once'),
      );
      expect(series.scheduleDescription, 'One-time');
    });

    test('scheduleDescription for biweekly', () {
      final series = Series(
        seriesId: 's-1',
        workspaceId: 'ws-1',
        kind: 'meeting',
        title: 'Test',
        scheduleRule: ScheduleRule(
          frequency: 'weekly',
          weekdays: [2],
          interval: 2,
        ),
      );
      expect(series.scheduleDescription, 'Every 2 weeks on Tue');
    });

    test('handles missing optional fields', () {
      final json = {
        'series_id': 's-2',
        'workspace_id': 'ws-1',
        'kind': 'reminder',
        'title': 'Reminder',
        'schedule_rule': {'frequency': 'once'},
      };
      final series = Series.fromJson(json);
      expect(series.defaultTime, isNull);
      expect(series.defaultDurationMinutes, isNull);
      expect(series.defaultLocation, isNull);
      expect(series.locationType, 'fixed');
      expect(series.status, 'active');
      expect(series.checkInWeekdays, isNull);
      expect(series.locationRotation, isNull);
    });
  });
}
