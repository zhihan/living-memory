import 'package:test/test.dart';
import 'package:event_ledger/models/workspace.dart';

void main() {
  group('Workspace.fromJson', () {
    test('parses minimal workspace', () {
      final json = {
        'workspace_id': 'ws-1',
        'title': 'Test Workspace',
        'type': 'shared',
        'timezone': 'Asia/Taipei',
        'owner_uids': ['uid-1'],
        'member_roles': {'uid-1': 'organizer'},
        'member_profiles': {},
      };
      final ws = Workspace.fromJson(json);
      expect(ws.workspaceId, 'ws-1');
      expect(ws.title, 'Test Workspace');
      expect(ws.type, 'shared');
      expect(ws.timezone, 'Asia/Taipei');
      expect(ws.ownerUids, ['uid-1']);
      expect(ws.memberRoles, {'uid-1': 'organizer'});
      expect(ws.description, isNull);
    });

    test('parses workspace with member profiles', () {
      final json = {
        'workspace_id': 'ws-2',
        'title': 'Study Group',
        'type': 'study',
        'timezone': 'UTC',
        'owner_uids': ['uid-1'],
        'member_roles': {'uid-1': 'organizer', 'uid-2': 'participant'},
        'member_profiles': {
          'uid-1': {'display_name': 'Alice', 'email': 'alice@test.com'},
          'uid-2': {'display_name': 'Bob', 'email': null},
        },
        'description': 'A study group',
      };
      final ws = Workspace.fromJson(json);
      expect(ws.memberProfiles['uid-1']!['display_name'], 'Alice');
      expect(ws.memberProfiles['uid-2']!['email'], isNull);
      expect(ws.description, 'A study group');
    });

    test('handles missing optional fields', () {
      final json = {
        'workspace_id': 'ws-3',
        'title': 'Minimal',
      };
      final ws = Workspace.fromJson(json);
      expect(ws.type, 'shared');
      expect(ws.timezone, 'UTC');
      expect(ws.ownerUids, isEmpty);
      expect(ws.memberRoles, isEmpty);
      expect(ws.memberProfiles, isEmpty);
    });
  });

  group('MemberDetail.fromJson', () {
    test('parses member detail', () {
      final json = {
        'uid': 'uid-1',
        'role': 'organizer',
        'display_name': 'Alice',
        'email': 'alice@test.com',
      };
      final detail = MemberDetail.fromJson(json);
      expect(detail.uid, 'uid-1');
      expect(detail.role, 'organizer');
      expect(detail.displayName, 'Alice');
      expect(detail.email, 'alice@test.com');
    });

    test('handles null display name and email', () {
      final json = {
        'uid': 'uid-2',
        'role': 'participant',
        'display_name': null,
        'email': null,
      };
      final detail = MemberDetail.fromJson(json);
      expect(detail.displayName, isNull);
      expect(detail.email, isNull);
    });
  });
}
