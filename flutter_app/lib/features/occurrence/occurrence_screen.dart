import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/check_in.dart';
import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../models/workspace.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';

class OccurrenceScreen extends StatefulWidget {
  final String occurrenceId;
  const OccurrenceScreen({super.key, required this.occurrenceId});

  @override
  State<OccurrenceScreen> createState() => _OccurrenceScreenState();
}

class _OccurrenceScreenState extends State<OccurrenceScreen> {
  Occurrence? _occurrence;
  Series? _series;
  Workspace? _workspace;
  CheckIn? _myCheckIn;
  List<CheckIn>? _allCheckIns;
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
      final occ = await api.getOccurrence(widget.occurrenceId);
      final results = await Future.wait([
        api.getSeries(occ.seriesId),
        api.getWorkspace(occ.workspaceId),
        api.getMyCheckIn(widget.occurrenceId),
      ]);
      final ws = results[1] as Workspace;
      final role = ws.memberRoles[_uid];
      List<CheckIn>? allCheckIns;
      if (role == 'organizer' || role == 'teacher') {
        allCheckIns = await api.listCheckIns(widget.occurrenceId);
      }
      if (mounted) {
        setState(() {
          _occurrence = occ;
          _series = results[0] as Series;
          _workspace = ws;
          _myCheckIn = results[2] as CheckIn?;
          _allCheckIns = allCheckIns;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _checkIn() async {
    try {
      await context.read<ApiService>().upsertCheckIn(
          widget.occurrenceId, 'confirmed');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _undoCheckIn() async {
    final ci = _myCheckIn;
    if (ci == null) return;
    try {
      await context.read<ApiService>().deleteCheckIn(ci.checkInId);
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _updateStatus(String status) async {
    try {
      await context.read<ApiService>().updateOccurrence(
          widget.occurrenceId, {'status': status});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _toggleCheckIn(bool enable) async {
    try {
      await context.read<ApiService>().updateOccurrence(
          widget.occurrenceId, {'enable_check_in': enable});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _editOverrides() async {
    final occ = _occurrence;
    if (occ == null) return;
    final titleCtrl =
        TextEditingController(text: occ.overrides?.title ?? '');
    final locationCtrl =
        TextEditingController(text: occ.effectiveLocation ?? '');
    final linkCtrl =
        TextEditingController(text: occ.overrides?.onlineLink ?? '');
    final notesCtrl =
        TextEditingController(text: occ.overrides?.notes ?? '');

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Occurrence'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: titleCtrl,
                  decoration: const InputDecoration(labelText: 'Title')),
              const SizedBox(height: 12),
              TextField(
                  controller: locationCtrl,
                  decoration: const InputDecoration(labelText: 'Location')),
              const SizedBox(height: 12),
              TextField(
                  controller: linkCtrl,
                  decoration: const InputDecoration(labelText: 'Online Link')),
              const SizedBox(height: 12),
              TextField(
                  controller: notesCtrl,
                  decoration: const InputDecoration(labelText: 'Notes'),
                  maxLines: 3),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () {
                Navigator.pop(ctx, {
                  'overrides': {
                    'title': titleCtrl.text,
                    'location': locationCtrl.text,
                    'online_link': linkCtrl.text,
                    'notes': notesCtrl.text,
                  },
                });
              },
              child: const Text('Save')),
        ],
      ),
    );
    if (result == null) return;
    try {
      await context
          .read<ApiService>()
          .updateOccurrence(widget.occurrenceId, result);
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
          appBar: AppBar(),
          body: const Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final occ = _occurrence!;
    final series = _series!;
    final dt = occ.scheduledDateTime.toLocal();
    final formatted = DateFormat('EEEE, MMM d, yyyy  HH:mm').format(dt);
    final effectiveLocation = occ.effectiveLocation ?? series.defaultLocation;
    final effectiveLink =
        occ.effectiveOnlineLink ?? series.defaultOnlineLink;
    final duration =
        occ.overrides?.durationMinutes ?? series.defaultDurationMinutes;

    return Scaffold(
      appBar: AppBar(
        title: Text(occ.effectiveTitle.isNotEmpty
            ? occ.effectiveTitle
            : series.title),
        actions: [
          if (_canManage)
            IconButton(
                onPressed: _editOverrides, icon: const Icon(Icons.edit)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Date & time
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(formatted,
                        style: Theme.of(context).textTheme.titleMedium),
                    if (duration != null) Text('Duration: $duration min'),
                    const SizedBox(height: 8),
                    _statusChip(occ.status),
                  ],
                ),
              ),
            ),

            // Location & link
            if (effectiveLocation != null || effectiveLink != null) ...[
              const SizedBox(height: 8),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (effectiveLocation != null)
                        Row(
                          children: [
                            const Icon(Icons.location_on, size: 18),
                            const SizedBox(width: 8),
                            Expanded(child: Text(effectiveLocation)),
                          ],
                        ),
                      if (effectiveLink != null) ...[
                        const SizedBox(height: 4),
                        InkWell(
                          onTap: () => launchUrl(Uri.parse(effectiveLink)),
                          child: Row(
                            children: [
                              const Icon(Icons.link, size: 18),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(effectiveLink,
                                    style: TextStyle(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .primary)),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],

            // Notes
            if (occ.effectiveNotes != null &&
                occ.effectiveNotes!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Notes',
                          style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: 4),
                      Text(occ.effectiveNotes!),
                    ],
                  ),
                ),
              ),
            ],

            // Organizer/teacher controls
            if (_canManage) ...[
              const SizedBox(height: 16),
              Text('Manage',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              // Status controls
              Wrap(
                spacing: 8,
                children: [
                  if (occ.status == 'scheduled') ...[
                    FilledButton(
                        onPressed: () => _updateStatus('completed'),
                        child: const Text('Complete')),
                    OutlinedButton(
                        onPressed: () => _updateStatus('cancelled'),
                        child: const Text('Cancel')),
                  ],
                ],
              ),
              const SizedBox(height: 8),
              SwitchListTile(
                title: const Text('Enable Check-in'),
                value: occ.enableCheckIn,
                onChanged: (v) => _toggleCheckIn(v),
              ),
            ],

            // Self check-in (participant)
            if (occ.enableCheckIn) ...[
              const SizedBox(height: 16),
              if (_myCheckIn == null ||
                  _myCheckIn!.status != 'confirmed')
                FilledButton.icon(
                  onPressed: _checkIn,
                  icon: const Icon(Icons.check),
                  label: const Text('Check In'),
                )
              else
                Row(
                  children: [
                    const Icon(Icons.check_circle, color: Colors.green),
                    const SizedBox(width: 8),
                    const Text('Checked in'),
                    const Spacer(),
                    TextButton(
                        onPressed: _undoCheckIn,
                        child: const Text('Undo')),
                  ],
                ),
            ],

            // All check-ins (organizer/teacher)
            if (_canManage && _allCheckIns != null) ...[
              const SizedBox(height: 16),
              Text('Check-ins (${_allCheckIns!.length})',
                  style: Theme.of(context).textTheme.titleMedium),
              if (_allCheckIns!.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(8),
                  child: Text('No check-ins yet.'),
                ),
              ..._allCheckIns!.map((ci) => ListTile(
                    dense: true,
                    leading: _checkInIcon(ci.status),
                    title:
                        Text(ci.displayName ?? ci.userId.substring(0, 8)),
                    subtitle: ci.note != null ? Text(ci.note!) : null,
                    trailing: Text(ci.status,
                        style: const TextStyle(fontSize: 12)),
                  )),
            ],
          ],
        ),
      ),
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
      label: Text(status),
      backgroundColor: color.withValues(alpha: 0.15),
      side: BorderSide.none,
    );
  }

  Widget _checkInIcon(String status) {
    return switch (status) {
      'confirmed' =>
        const Icon(Icons.check_circle, color: Colors.green, size: 20),
      'declined' => const Icon(Icons.cancel, color: Colors.red, size: 20),
      'missed' =>
        const Icon(Icons.remove_circle, color: Colors.orange, size: 20),
      _ =>
        const Icon(Icons.hourglass_empty, color: Colors.grey, size: 20),
    };
  }
}
