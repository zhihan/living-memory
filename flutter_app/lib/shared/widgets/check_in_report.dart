import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../models/check_in.dart';
import '../../models/occurrence.dart';
import '../../services/api_service.dart';

class CheckInReportWidget extends StatefulWidget {
  final String seriesId;
  const CheckInReportWidget({super.key, required this.seriesId});

  @override
  State<CheckInReportWidget> createState() => _CheckInReportWidgetState();
}

class _CheckInReportWidgetState extends State<CheckInReportWidget> {
  Map<String, dynamic>? _report;
  bool _loading = false;
  bool _expanded = false;
  int _windowSize = 10;

  Future<void> _loadReport() async {
    setState(() => _loading = true);
    try {
      final data = await context
          .read<ApiService>()
          .getCheckInReport(widget.seriesId);
      if (mounted) setState(() => _report = data);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error loading report: $e')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            setState(() => _expanded = !_expanded);
            if (_expanded && _report == null) _loadReport();
          },
          child: Row(
            children: [
              Text('Check-in Report',
                  style: Theme.of(context).textTheme.titleMedium),
              Icon(_expanded ? Icons.expand_less : Icons.expand_more),
            ],
          ),
        ),
        if (_expanded) ...[
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_report != null)
            _buildReport(),
        ],
      ],
    );
  }

  Widget _buildReport() {
    final report = _report!;
    final rawOccs = report['occurrences'] as List;
    final rawCheckIns = report['check_ins'] as List;
    final memberRoles =
        Map<String, String>.from(report['members'] as Map? ?? {});
    final memberProfiles =
        report['member_profiles'] as Map<String, dynamic>? ?? {};

    final occs = rawOccs
        .map((o) => Occurrence.fromJson(o as Map<String, dynamic>))
        .toList();
    final checkIns = rawCheckIns
        .map((c) => CheckIn.fromJson(c as Map<String, dynamic>))
        .toList();

    // Limit to window
    final displayOccs = occs.length > _windowSize
        ? occs.sublist(occs.length - _windowSize)
        : occs;

    // Build lookup: occurrenceId -> userId -> checkIn
    final lookup = <String, Map<String, CheckIn>>{};
    for (final ci in checkIns) {
      lookup.putIfAbsent(ci.occurrenceId, () => {})[ci.userId] = ci;
    }

    // Get all member UIDs
    final memberUids = memberRoles.keys.toList();

    if (displayOccs.isEmpty || memberUids.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(8),
        child: Text('No check-in data.'),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Window selector
        Row(
          children: [
            const Text('Show last: '),
            DropdownButton<int>(
              value: _windowSize,
              items: const [
                DropdownMenuItem(value: 5, child: Text('5')),
                DropdownMenuItem(value: 10, child: Text('10')),
                DropdownMenuItem(value: 20, child: Text('20')),
                DropdownMenuItem(value: 50, child: Text('All')),
              ],
              onChanged: (v) {
                setState(() => _windowSize = v!);
              },
            ),
          ],
        ),
        const SizedBox(height: 8),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columnSpacing: 12,
            columns: [
              const DataColumn(label: Text('Member')),
              ...displayOccs.map((o) {
                final dt = DateTime.parse(o.scheduledFor).toLocal();
                return DataColumn(
                    label: Text(DateFormat('M/d').format(dt),
                        style: const TextStyle(fontSize: 11)));
              }),
            ],
            rows: memberUids.map((uid) {
              final profile = memberProfiles[uid] as Map<String, dynamic>?;
              final name = profile?['display_name'] as String? ??
                  uid.substring(0, 8);
              return DataRow(cells: [
                DataCell(Text(name, style: const TextStyle(fontSize: 12))),
                ...displayOccs.map((o) {
                  final ci = lookup[o.occurrenceId]?[uid];
                  return DataCell(_statusIcon(ci?.status));
                }),
              ]);
            }).toList(),
          ),
        ),
      ],
    );
  }

  Widget _statusIcon(String? status) {
    return switch (status) {
      'confirmed' =>
        const Icon(Icons.check_circle, color: Colors.green, size: 18),
      'declined' =>
        const Icon(Icons.cancel, color: Colors.red, size: 18),
      'missed' =>
        const Icon(Icons.remove_circle, color: Colors.orange, size: 18),
      'pending' =>
        const Icon(Icons.hourglass_empty, color: Colors.grey, size: 18),
      _ => const Icon(Icons.horizontal_rule, color: Colors.grey, size: 18),
    };
  }
}
