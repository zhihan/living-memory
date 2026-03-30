import 'package:test/test.dart';
import 'package:event_ledger/models/check_in.dart';

void main() {
  group('CheckIn.fromJson', () {
    test('parses confirmed check-in', () {
      final json = {
        'check_in_id': 'ci-1',
        'occurrence_id': 'occ-1',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'user_id': 'uid-1',
        'display_name': 'Alice',
        'status': 'confirmed',
        'checked_in_at': '2026-04-01T14:05:00+00:00',
        'note': 'Present',
      };
      final ci = CheckIn.fromJson(json);
      expect(ci.checkInId, 'ci-1');
      expect(ci.userId, 'uid-1');
      expect(ci.displayName, 'Alice');
      expect(ci.status, 'confirmed');
      expect(ci.checkedInAt, '2026-04-01T14:05:00+00:00');
      expect(ci.note, 'Present');
    });

    test('handles missing optional fields', () {
      final json = {
        'check_in_id': 'ci-2',
        'occurrence_id': 'occ-1',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'user_id': 'uid-2',
      };
      final ci = CheckIn.fromJson(json);
      expect(ci.displayName, isNull);
      expect(ci.status, 'pending');
      expect(ci.checkedInAt, isNull);
      expect(ci.note, isNull);
    });

    test('parses declined check-in', () {
      final json = {
        'check_in_id': 'ci-3',
        'occurrence_id': 'occ-1',
        'series_id': 's-1',
        'workspace_id': 'ws-1',
        'user_id': 'uid-3',
        'status': 'declined',
        'note': 'Cannot attend',
      };
      final ci = CheckIn.fromJson(json);
      expect(ci.status, 'declined');
      expect(ci.note, 'Cannot attend');
    });
  });
}
