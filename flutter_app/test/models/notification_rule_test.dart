import 'package:test/test.dart';
import 'package:event_ledger/models/notification_rule.dart';

void main() {
  group('NotificationRule.fromJson', () {
    test('parses full rule', () {
      final json = {
        'rule_id': 'r-1',
        'workspace_id': 'ws-1',
        'series_id': 's-1',
        'channel': 'telegram',
        'remind_before_minutes': 60,
        'enabled': true,
        'target_roles': ['participant', 'student'],
      };
      final rule = NotificationRule.fromJson(json);
      expect(rule.ruleId, 'r-1');
      expect(rule.seriesId, 's-1');
      expect(rule.channel, 'telegram');
      expect(rule.remindBeforeMinutes, 60);
      expect(rule.enabled, true);
      expect(rule.targetRoles, ['participant', 'student']);
    });

    test('handles workspace-level rule (null series_id)', () {
      final json = {
        'rule_id': 'r-2',
        'workspace_id': 'ws-1',
        'series_id': null,
        'channel': 'email',
        'remind_before_minutes': 30,
      };
      final rule = NotificationRule.fromJson(json);
      expect(rule.seriesId, isNull);
      expect(rule.enabled, true);
      expect(rule.targetRoles, isEmpty);
    });
  });
}
