import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../models/workspace.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../shared/widgets/check_in_report.dart';

class SeriesScreen extends StatefulWidget {
  final String seriesId;
  const SeriesScreen({super.key, required this.seriesId});

  @override
  State<SeriesScreen> createState() => _SeriesScreenState();
}

class _SeriesScreenState extends State<SeriesScreen> {
  Series? _series;
  Workspace? _workspace;
  List<Occurrence>? _occurrences;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  bool get _canManage {
    final ws = _workspace;
    if (ws == null) return false;
    final role = ws.memberRoles[_uid];
    return role == 'organizer' || role == 'teacher';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiService>();
      final series = await api.getSeries(widget.seriesId);
      final results = await Future.wait([
        api.getWorkspace(series.workspaceId),
        api.listSeriesOccurrences(widget.seriesId),
      ]);
      if (mounted) {
        setState(() {
          _series = series;
          _workspace = results[0] as Workspace;
          _occurrences = results[1] as List<Occurrence>;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generateOccurrences() async {
    final now = DateTime.now();
    final start = DateFormat('yyyy-MM-dd').format(now);
    final end =
        DateFormat('yyyy-MM-dd').format(now.add(const Duration(days: 90)));
    try {
      final result = await context
          .read<ApiService>()
          .generateOccurrences(widget.seriesId, start, end);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Generated ${result['created']} occurrences')));
        _load();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _editSeries() async {
    final series = _series;
    if (series == null) return;
    final titleCtrl = TextEditingController(text: series.title);
    final descCtrl = TextEditingController(text: series.description ?? '');
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Series'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
                controller: titleCtrl,
                decoration: const InputDecoration(labelText: 'Title')),
            const SizedBox(height: 12),
            TextField(
                controller: descCtrl,
                decoration: const InputDecoration(labelText: 'Description'),
                maxLines: 2),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
              onPressed: () {
                final updates = <String, dynamic>{};
                if (titleCtrl.text.trim() != series.title) {
                  updates['title'] = titleCtrl.text.trim();
                }
                if (descCtrl.text.trim() != (series.description ?? '')) {
                  updates['description'] = descCtrl.text.trim();
                }
                Navigator.pop(ctx, updates.isEmpty ? null : updates);
              },
              child: const Text('Save')),
        ],
      ),
    );
    if (result == null) return;
    try {
      await context.read<ApiService>().updateSeries(widget.seriesId, result);
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
          appBar: AppBar(), body: const Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final series = _series!;
    final occs = _occurrences ?? [];
    final cs = Theme.of(context).colorScheme;
    final now = DateTime.now().toUtc();
    final upcoming =
        occs.where((o) => o.scheduledDateTime.isAfter(now) && o.status == 'scheduled').toList()
          ..sort((a, b) => a.scheduledFor.compareTo(b.scheduledFor));
    final past =
        occs.where((o) => o.scheduledDateTime.isBefore(now) || o.status != 'scheduled').toList()
          ..sort((a, b) => b.scheduledFor.compareTo(a.scheduledFor));

    return Scaffold(
      appBar: AppBar(
        title: Text(series.title),
        actions: [
          if (_canManage)
            IconButton(onPressed: _editSeries, icon: const Icon(Icons.edit)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
          children: [
            // Series info card
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _infoRow(Icons.schedule, series.scheduleDescription, cs),
                    if (series.defaultTime != null)
                      _infoRow(Icons.access_time, 'Time: ${series.defaultTime}', cs),
                    if (series.defaultDurationMinutes != null)
                      _infoRow(Icons.timelapse, '${series.defaultDurationMinutes} min', cs),
                    if (series.defaultLocation != null)
                      _infoRow(Icons.location_on_outlined, series.defaultLocation!, cs),
                    if (series.defaultOnlineLink != null)
                      _infoRow(Icons.link, series.defaultOnlineLink!, cs),
                    if (series.description != null &&
                        series.description!.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(series.description!,
                          style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                    ],
                  ],
                ),
              ),
            ),

            // Next meeting
            if (upcoming.isNotEmpty) ...[
              const SizedBox(height: 16),
              _sectionLabel('Next Meeting', cs),
              const SizedBox(height: 6),
              _meetingCard(upcoming.first, cs, isNext: true),
            ],

            // Last meeting
            if (past.isNotEmpty) ...[
              const SizedBox(height: 12),
              _sectionLabel('Last Meeting', cs),
              const SizedBox(height: 6),
              _meetingCard(past.first, cs, isPast: true),
            ],

            // Generate button
            if (_canManage) ...[
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _generateOccurrences,
                icon: const Icon(Icons.add_circle_outline, size: 18),
                label: const Text('Generate next 90 days'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(40),
                ),
              ),
            ],

            // Upcoming list
            if (upcoming.length > 1) ...[
              const SizedBox(height: 16),
              _sectionLabel('Upcoming', cs),
              const SizedBox(height: 6),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: upcoming.skip(1).take(10).toList().asMap().entries.map((entry) {
                    final occ = entry.value;
                    final isLast = entry.key == (upcoming.length - 2).clamp(0, 9);
                    return Column(
                      children: [
                        _occurrenceListItem(occ, cs),
                        if (!isLast)
                          Divider(height: 1, indent: 16, endIndent: 16,
                              color: cs.outlineVariant.withValues(alpha: 0.4)),
                      ],
                    );
                  }).toList(),
                ),
              ),
            ],

            // Check-in report
            if (_canManage) ...[
              const SizedBox(height: 16),
              CheckInReportWidget(seriesId: widget.seriesId),
            ],
          ],
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String text, ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Icon(icon, size: 16, color: cs.onSurfaceVariant),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text,
                style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
                overflow: TextOverflow.ellipsis),
          ),
        ],
      ),
    );
  }

  Widget _sectionLabel(String text, ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Text(text,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
            color: cs.onSurfaceVariant,
          )),
    );
  }

  Widget _meetingCard(Occurrence occ, ColorScheme cs,
      {bool isNext = false, bool isPast = false}) {
    final dt = occ.scheduledDateTime.toLocal();
    final dateStr = DateFormat('E, MMM d').format(dt);
    final timeStr = DateFormat('HH:mm').format(dt);
    final statusColor = _statusColor(occ.status);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/occurrences/${occ.occurrenceId}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: isNext
                      ? cs.primaryContainer
                      : cs.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(DateFormat('d').format(dt),
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 16,
                            color: isNext ? cs.onPrimaryContainer : cs.onSurface)),
                    Text(DateFormat('MMM').format(dt),
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w500,
                            color: isNext ? cs.onPrimaryContainer : cs.onSurfaceVariant)),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      occ.effectiveTitle.isNotEmpty
                          ? occ.effectiveTitle
                          : dateStr,
                      style: TextStyle(
                        fontWeight: FontWeight.w500,
                        fontSize: 14,
                        color: isPast ? cs.onSurfaceVariant : cs.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      occ.effectiveTitle.isNotEmpty ? '$dateStr  $timeStr' : timeStr,
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                    ),
                    if (occ.effectiveLocation != null) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Icon(Icons.location_on_outlined, size: 12,
                              color: cs.onSurfaceVariant),
                          const SizedBox(width: 3),
                          Expanded(
                            child: Text(occ.effectiveLocation!,
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                                overflow: TextOverflow.ellipsis),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(occ.status,
                    style: TextStyle(fontSize: 11, color: statusColor,
                        fontWeight: FontWeight.w500)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _occurrenceListItem(Occurrence occ, ColorScheme cs) {
    final dt = occ.scheduledDateTime.toLocal();
    final dateStr = DateFormat('E, MMM d').format(dt);
    final timeStr = DateFormat('HH:mm').format(dt);

    return InkWell(
      onTap: () => context.push('/occurrences/${occ.occurrenceId}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            SizedBox(
              width: 28,
              child: Text(DateFormat('d').format(dt),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                      color: cs.onSurface)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$dateStr  $timeStr',
                      style: TextStyle(fontSize: 13, color: cs.onSurface)),
                  if (occ.effectiveLocation != null)
                    Text(occ.effectiveLocation!,
                        style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                        overflow: TextOverflow.ellipsis),
                ],
              ),
            ),
            Icon(Icons.chevron_right, size: 18, color: cs.onSurfaceVariant),
          ],
        ),
      ),
    );
  }

  Color _statusColor(String status) {
    return switch (status) {
      'scheduled' => Colors.blue,
      'completed' => Colors.green,
      'cancelled' => Colors.grey,
      'rescheduled' => Colors.orange,
      _ => Colors.grey,
    };
  }
}
