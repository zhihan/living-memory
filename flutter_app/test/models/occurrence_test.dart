import 'package:test/test.dart';
import 'package:event_ledger/models/occurrence.dart';

void main() {
  group('Occurrence.fromJson', () {
    test('parses basic occurrence', () {
      final json = {
        'occurrence_id': 'occ-1',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'scheduled_for': '2026-04-01T14:00:00+00:00',
        'status': 'scheduled',
        'location': 'Room A',
        'enable_check_in': true,
        'sequence_index': 0,
      };
      final occ = Occurrence.fromJson(json);
      expect(occ.occurrenceId, 'occ-1');
      expect(occ.seriesId, 's-1');
      expect(occ.scheduledFor, '2026-04-01T14:00:00+00:00');
      expect(occ.status, 'scheduled');
      expect(occ.location, 'Room A');
      expect(occ.enableCheckIn, true);
      expect(occ.sequenceIndex, 0);
      expect(occ.overrides, isNull);
    });

    test('parses occurrence with overrides', () {
      final json = {
        'occurrence_id': 'occ-2',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'scheduled_for': '2026-04-02T14:00:00+00:00',
        'overrides': {
          'title': 'Special Session',
          'location': 'Room B',
          'online_link': 'https://zoom.us/123',
          'notes': 'Bring laptop',
          'duration_minutes': 90,
        },
      };
      final occ = Occurrence.fromJson(json);
      expect(occ.overrides, isNotNull);
      expect(occ.overrides!.title, 'Special Session');
      expect(occ.overrides!.location, 'Room B');
      expect(occ.overrides!.onlineLink, 'https://zoom.us/123');
      expect(occ.overrides!.notes, 'Bring laptop');
      expect(occ.overrides!.durationMinutes, 90);
    });

    test('effective fields prefer overrides', () {
      final occ = Occurrence(
        occurrenceId: 'occ-3',
        seriesId: 's-1',
        workspaceId: 'ws-1',
        scheduledFor: '2026-04-03T10:00:00+00:00',
        location: 'Default Room',
        overrides: OccurrenceOverrides(
          location: 'Override Room',
          title: 'Override Title',
        ),
      );
      expect(occ.effectiveTitle, 'Override Title');
      expect(occ.effectiveLocation, 'Override Room');
    });

    test('effective fields fall back without overrides', () {
      final occ = Occurrence(
        occurrenceId: 'occ-4',
        seriesId: 's-1',
        workspaceId: 'ws-1',
        scheduledFor: '2026-04-04T10:00:00+00:00',
        location: 'Default Room',
      );
      expect(occ.effectiveTitle, '');
      expect(occ.effectiveLocation, 'Default Room');
      expect(occ.effectiveOnlineLink, isNull);
      expect(occ.effectiveNotes, isNull);
    });

    test('scheduledDateTime parses correctly', () {
      final occ = Occurrence(
        occurrenceId: 'occ-5',
        seriesId: 's-1',
        workspaceId: 'ws-1',
        scheduledFor: '2026-04-01T14:00:00+00:00',
      );
      final dt = occ.scheduledDateTime;
      expect(dt.year, 2026);
      expect(dt.month, 4);
      expect(dt.day, 1);
      expect(dt.hour, 14);
      expect(dt.isUtc, true);
    });

    test('defaults for missing fields', () {
      final json = {
        'occurrence_id': 'occ-6',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'scheduled_for': '2026-04-05T10:00:00+00:00',
      };
      final occ = Occurrence.fromJson(json);
      expect(occ.status, 'scheduled');
      expect(occ.enableCheckIn, false);
      expect(occ.location, isNull);
      expect(occ.overrides, isNull);
      expect(occ.sequenceIndex, isNull);
    });
  });

  group('OccurrenceOverrides.toJson', () {
    test('only includes non-null fields', () {
      final overrides = OccurrenceOverrides(
        title: 'Custom',
        notes: 'Notes here',
      );
      final json = overrides.toJson();
      expect(json['title'], 'Custom');
      expect(json['notes'], 'Notes here');
      expect(json.containsKey('location'), false);
      expect(json.containsKey('online_link'), false);
    });
  });
}
