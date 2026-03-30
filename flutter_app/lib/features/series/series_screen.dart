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
          padding: const EdgeInsets.all(16),
          children: [
            // Series info card
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(series.scheduleDescription,
                        style: Theme.of(context).textTheme.titleSmall),
                    if (series.defaultTime != null)
                      Text('Time: ${series.defaultTime}'),
                    if (series.defaultDurationMinutes != null)
                      Text('Duration: ${series.defaultDurationMinutes} min'),
                    if (series.defaultLocation != null)
                      Text('Location: ${series.defaultLocation}'),
                    if (series.defaultOnlineLink != null)
                      Text('Link: ${series.defaultOnlineLink}'),
                    Text('Location mode: ${series.locationType}'),
                    if (series.description != null &&
                        series.description!.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(series.description!),
                    ],
                  ],
                ),
              ),
            ),

            // Next meeting
            if (upcoming.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Next Meeting',
                  style: Theme.of(context).textTheme.titleMedium),
              _occurrenceTile(upcoming.first),
            ],

            // Last meeting
            if (past.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Last Meeting',
                  style: Theme.of(context).textTheme.titleMedium),
              _occurrenceTile(past.first),
            ],

            // Generate button
            if (_canManage) ...[
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: _generateOccurrences,
                icon: const Icon(Icons.add_circle_outline),
                label: const Text('Generate Occurrences (next 90 days)'),
              ),
            ],

            // Upcoming list
            if (upcoming.length > 1) ...[
              const SizedBox(height: 16),
              Text('Upcoming',
                  style: Theme.of(context).textTheme.titleMedium),
              ...upcoming.skip(1).map(_occurrenceTile),
            ],

            // Check-in report
            if (_canManage) ...[
              const SizedBox(height: 24),
              CheckInReportWidget(seriesId: widget.seriesId),
            ],
          ],
        ),
      ),
    );
  }

  Widget _occurrenceTile(Occurrence occ) {
    final dt = occ.scheduledDateTime.toLocal();
    final formatted = DateFormat('E, MMM d, yyyy  HH:mm').format(dt);
    return ListTile(
      title: Text(occ.effectiveTitle.isNotEmpty
          ? occ.effectiveTitle
          : formatted),
      subtitle: occ.effectiveTitle.isNotEmpty ? Text(formatted) : null,
      trailing: _statusChip(occ.status),
      onTap: () => context.push('/occurrences/${occ.occurrenceId}'),
    );
  }

  Widget _statusChip(String status) {
    final color = switch (status) {
      'scheduled' => Colors.blue,
      'completed' => Colors.green,
      'cancelled' => Colors.grey,
      'rescheduled' => Colors.orange,
      _ => Colors.grey,
    };
    return Chip(
      label: Text(status, style: const TextStyle(fontSize: 11)),
      backgroundColor: color.withValues(alpha: 0.15),
      side: BorderSide.none,
      visualDensity: VisualDensity.compact,
    );
  }
}
