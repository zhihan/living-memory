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

  // Inline location editing
  String? _editingLocationOccId;
  final _locationEditCtrl = TextEditingController();

  // Inline agenda editing
  bool _editingAgenda = false;
  final _agendaCtrl = TextEditingController();
  bool _agendaSaving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _locationEditCtrl.dispose();
    _agendaCtrl.dispose();
    super.dispose();
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
        DateFormat('yyyy-MM-dd').format(now.add(const Duration(days: 60)));
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

  Future<void> _saveInlineLocation(Occurrence occ) async {
    final newLoc = _locationEditCtrl.text.trim();
    final oldLoc = occ.location ?? '';
    setState(() => _editingLocationOccId = null);
    if (newLoc == oldLoc) return;
    try {
      await context.read<ApiService>().updateOccurrence(
          occ.occurrenceId, {'location': newLoc.isNotEmpty ? newLoc : null});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _saveAgenda(String occurrenceId) async {
    setState(() => _agendaSaving = true);
    try {
      final notes = _agendaCtrl.text.trim();
      await context.read<ApiService>().updateOccurrence(
          occurrenceId, {
        'overrides': {'notes': notes.isNotEmpty ? notes : null},
      });
      setState(() => _editingAgenda = false);
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    } finally {
      if (mounted) setState(() => _agendaSaving = false);
    }
  }

  Future<void> _editSeries() async {
    final series = _series;
    if (series == null) return;
    final titleCtrl = TextEditingController(text: series.title);
    final descCtrl = TextEditingController(text: series.description ?? '');
    final timeCtrl = TextEditingController(text: series.defaultTime ?? '');
    final durationCtrl = TextEditingController(
        text: series.defaultDurationMinutes?.toString() ?? '');
    final locationCtrl =
        TextEditingController(text: series.defaultLocation ?? '');
    final linkCtrl =
        TextEditingController(text: series.defaultOnlineLink ?? '');
    var locationType = series.locationType;
    var checkInWeekdays = List<int>.from(series.checkInWeekdays ?? []);
    String? extendDate;
    var hostRotationMode = series.hostRotationMode;
    var hostRotation = List<String>.from(series.hostRotation ?? []);
    var hostAddresses = Map<String, String>.from(series.hostAddresses ?? {});

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Edit Series'),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                      controller: titleCtrl,
                      decoration: const InputDecoration(labelText: 'Title')),
                  const SizedBox(height: 12),
                  TextField(
                      controller: descCtrl,
                      decoration:
                          const InputDecoration(labelText: 'Description'),
                      maxLines: 2),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                            controller: timeCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Time', hintText: 'HH:MM')),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                            controller: durationCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Duration (min)'),
                            keyboardType: TextInputType.number),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: locationType,
                    decoration:
                        const InputDecoration(labelText: 'Location Type'),
                    items: const [
                      DropdownMenuItem(
                          value: 'fixed', child: Text('Fixed')),
                      DropdownMenuItem(
                          value: 'per_occurrence',
                          child: Text('Per Meeting')),
                      DropdownMenuItem(
                          value: 'rotation', child: Text('Rotation')),
                    ],
                    onChanged: (v) =>
                        setDialogState(() => locationType = v!),
                  ),
                  if (locationType == 'fixed') ...[
                    const SizedBox(height: 12),
                    TextField(
                        controller: locationCtrl,
                        decoration:
                            const InputDecoration(labelText: 'Location')),
                  ],
                  const SizedBox(height: 12),
                  TextField(
                      controller: linkCtrl,
                      decoration:
                          const InputDecoration(labelText: 'Online Link')),
                  if (series.scheduleRule.weekdays.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    const Text('Check-in days',
                        style: TextStyle(fontSize: 12)),
                    const SizedBox(height: 4),
                    Wrap(
                      spacing: 4,
                      children: {
                        1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu',
                        5: 'Fri', 6: 'Sat', 7: 'Sun',
                      }.entries.where((e) {
                        return series.scheduleRule.weekdays.contains(e.key);
                      }).map((e) {
                        return FilterChip(
                          label: Text(e.value),
                          selected: checkInWeekdays.contains(e.key),
                          onSelected: (sel) {
                            setDialogState(() {
                              if (sel) {
                                checkInWeekdays.add(e.key);
                              } else {
                                checkInWeekdays.remove(e.key);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                  ],
                  const SizedBox(height: 12),
                  InkWell(
                    onTap: () async {
                      final picked = await showDatePicker(
                        context: ctx,
                        initialDate: DateTime.now().add(
                            const Duration(days: 30)),
                        firstDate: DateTime.now(),
                        lastDate: DateTime.now().add(
                            const Duration(days: 365)),
                      );
                      if (picked != null) {
                        setDialogState(() {
                          extendDate =
                              DateFormat('yyyy-MM-dd').format(picked);
                        });
                      }
                    },
                    child: InputDecorator(
                      decoration: const InputDecoration(
                          labelText: 'Extend schedule to'),
                      child: Text(
                          extendDate ?? 'Tap to select date',
                          style: TextStyle(
                              color: extendDate != null
                                  ? null
                                  : Theme.of(ctx)
                                      .colorScheme
                                      .onSurfaceVariant)),
                    ),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: hostRotationMode,
                    decoration: const InputDecoration(labelText: 'Host Rotation'),
                    items: const [
                      DropdownMenuItem(value: 'none', child: Text('None')),
                      DropdownMenuItem(value: 'host_only', child: Text('Host only')),
                      DropdownMenuItem(value: 'host_and_location', child: Text('Host + Location')),
                    ],
                    onChanged: (v) => setDialogState(() => hostRotationMode = v!),
                  ),
                  if (hostRotationMode != 'none') ...[
                    const SizedBox(height: 12),
                    const Text('Rotation Order', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Container(
                      constraints: const BoxConstraints(maxHeight: 200),
                      decoration: BoxDecoration(
                        border: Border.all(color: Theme.of(ctx).colorScheme.outlineVariant),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: hostRotation.isEmpty
                          ? Padding(
                              padding: const EdgeInsets.all(16),
                              child: Text('No hosts added',
                                  style: TextStyle(color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
                            )
                          : ReorderableListView.builder(
                              shrinkWrap: true,
                              itemCount: hostRotation.length,
                              onReorder: (oldIndex, newIndex) {
                                setDialogState(() {
                                  if (newIndex > oldIndex) newIndex--;
                                  final host = hostRotation.removeAt(oldIndex);
                                  hostRotation.insert(newIndex, host);
                                });
                              },
                              itemBuilder: (ctx, index) {
                                final host = hostRotation[index];
                                return ListTile(
                                  key: ValueKey(host + index.toString()),
                                  leading: const Icon(Icons.drag_handle),
                                  title: Text(host, style: const TextStyle(fontSize: 14)),
                                  subtitle: hostRotationMode == 'host_and_location' && hostAddresses.containsKey(host)
                                      ? Text('📍 ${hostAddresses[host]}', style: const TextStyle(fontSize: 12))
                                      : null,
                                  trailing: IconButton(
                                    icon: const Icon(Icons.remove_circle_outline),
                                    onPressed: () {
                                      setDialogState(() {
                                        hostRotation.removeAt(index);
                                        hostAddresses.remove(host);
                                      });
                                    },
                                  ),
                                  onTap: hostRotationMode == 'host_and_location'
                                      ? () async {
                                          final locationCtrl = TextEditingController(text: hostAddresses[host] ?? '');
                                          final location = await showDialog<String>(
                                            context: ctx,
                                            builder: (dialogCtx) => AlertDialog(
                                              title: Text('Location for $host'),
                                              content: TextField(
                                                controller: locationCtrl,
                                                decoration: const InputDecoration(
                                                  labelText: 'Address',
                                                  hintText: '123 Main St',
                                                ),
                                                autofocus: true,
                                              ),
                                              actions: [
                                                TextButton(
                                                  onPressed: () => Navigator.pop(dialogCtx),
                                                  child: const Text('Cancel'),
                                                ),
                                                FilledButton(
                                                  onPressed: () => Navigator.pop(dialogCtx, locationCtrl.text),
                                                  child: const Text('Save'),
                                                ),
                                              ],
                                            ),
                                          );
                                          if (location != null) {
                                            setDialogState(() {
                                              hostAddresses[host] = location;
                                            });
                                          }
                                        }
                                      : null,
                                );
                              },
                            ),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: () async {
                        final hostCtrl = TextEditingController();
                        final locationCtrl = TextEditingController();
                        final result = await showDialog<Map<String, String>>(
                          context: ctx,
                          builder: (dialogCtx) => AlertDialog(
                            title: const Text('Add Host'),
                            content: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                TextField(
                                  controller: hostCtrl,
                                  decoration: const InputDecoration(
                                    labelText: 'Host Name',
                                    hintText: 'Team A, Alice, etc.',
                                  ),
                                  autofocus: true,
                                ),
                                if (hostRotationMode == 'host_and_location') ...[
                                  const SizedBox(height: 12),
                                  TextField(
                                    controller: locationCtrl,
                                    decoration: const InputDecoration(
                                      labelText: 'Address',
                                      hintText: '123 Main St',
                                    ),
                                  ),
                                ],
                              ],
                            ),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(dialogCtx),
                                child: const Text('Cancel'),
                              ),
                              FilledButton(
                                onPressed: () {
                                  Navigator.pop(dialogCtx, {
                                    'host': hostCtrl.text,
                                    'location': locationCtrl.text,
                                  });
                                },
                                child: const Text('Add'),
                              ),
                            ],
                          ),
                        );
                        if (result != null && result['host']!.trim().isNotEmpty) {
                          setDialogState(() {
                            final hostName = result['host']!.trim();
                            hostRotation.add(hostName);
                            if (hostRotationMode == 'host_and_location' && result['location']!.trim().isNotEmpty) {
                              hostAddresses[hostName] = result['location']!.trim();
                            }
                          });
                        }
                      },
                      icon: const Icon(Icons.person_add, size: 18),
                      label: const Text('Add Host'),
                      style: OutlinedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel')),
            FilledButton(
                onPressed: () {
                  final updates = <String, dynamic>{};
                  if (titleCtrl.text.trim() != series.title) {
                    updates['title'] = titleCtrl.text.trim();
                  }
                  if (descCtrl.text.trim() != (series.description ?? '')) {
                    updates['description'] = descCtrl.text.trim();
                  }
                  if (timeCtrl.text.trim() != (series.defaultTime ?? '')) {
                    updates['default_time'] = timeCtrl.text.trim();
                  }
                  final dur = int.tryParse(durationCtrl.text);
                  if (dur != series.defaultDurationMinutes) {
                    updates['default_duration_minutes'] = dur;
                  }
                  if (locationCtrl.text.trim() !=
                      (series.defaultLocation ?? '')) {
                    updates['default_location'] =
                        locationCtrl.text.trim().isNotEmpty
                            ? locationCtrl.text.trim()
                            : null;
                  }
                  if (linkCtrl.text.trim() !=
                      (series.defaultOnlineLink ?? '')) {
                    updates['default_online_link'] =
                        linkCtrl.text.trim().isNotEmpty
                            ? linkCtrl.text.trim()
                            : null;
                  }
                  if (locationType != series.locationType) {
                    updates['location_type'] = locationType;
                  }
                  updates['check_in_weekdays'] = checkInWeekdays;
                  if (hostRotationMode != series.hostRotationMode) {
                    updates['host_rotation_mode'] = hostRotationMode;
                  }
                  if (hostRotation != (series.hostRotation ?? [])) {
                    updates['host_rotation'] = hostRotation;
                  }
                  if (hostAddresses != (series.hostAddresses ?? {})) {
                    updates['host_addresses'] = hostAddresses;
                  }
                  if (extendDate != null) {
                    updates['_extend_date'] = extendDate;
                  }
                  Navigator.pop(
                      ctx, updates.length <= 3 && extendDate == null ? null : updates);
                },
                child: const Text('Save')),
          ],
        ),
      ),
    );
    if (result == null) return;

    try {
      final extDate = result.remove('_extend_date') as String?;
      if (result.isNotEmpty) {
        await context.read<ApiService>().updateSeries(widget.seriesId, result);
      }
      if (extDate != null) {
        final now = DateTime.now();
        final start = DateFormat('yyyy-MM-dd').format(now);
        await context
            .read<ApiService>()
            .generateOccurrences(widget.seriesId, start, extDate);
      }
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

            // Last meeting
            if (past.isNotEmpty) ...[
              const SizedBox(height: 12),
              _sectionLabel('Last Meeting', cs),
              const SizedBox(height: 6),
              _meetingCard(past.first, cs, isPast: true),
            ],

            // Next meeting with agenda editing
            if (upcoming.isNotEmpty) ...[
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(child: _sectionLabel('Next Meeting', cs)),
                  if (_canManage && !_editingAgenda)
                    TextButton(
                      onPressed: () {
                        final notes = upcoming.first.effectiveNotes ?? '';
                        _agendaCtrl.text = notes;
                        setState(() => _editingAgenda = true);
                      },
                      style: TextButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        textStyle: const TextStyle(fontSize: 12),
                      ),
                      child: Text(upcoming.first.effectiveNotes != null
                          ? 'Edit agenda'
                          : 'Add agenda'),
                    ),
                ],
              ),
              const SizedBox(height: 6),
              _meetingCard(upcoming.first, cs, isNext: true),
              if (_editingAgenda) ...[
                const SizedBox(height: 8),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: _agendaCtrl,
                          maxLines: 3,
                          decoration: const InputDecoration(
                            hintText: 'Agenda, discussion topics...',
                            border: OutlineInputBorder(),
                            isDense: true,
                          ),
                          enabled: !_agendaSaving,
                        ),
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            TextButton(
                              onPressed: _agendaSaving
                                  ? null
                                  : () => setState(() => _editingAgenda = false),
                              child: const Text('Cancel'),
                            ),
                            const SizedBox(width: 8),
                            FilledButton(
                              onPressed: _agendaSaving
                                  ? null
                                  : () => _saveAgenda(
                                      upcoming.first.occurrenceId),
                              child: Text(
                                  _agendaSaving ? 'Saving...' : 'Save'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ] else if (upcoming.first.effectiveNotes != null) ...[
                const SizedBox(height: 4),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Text(upcoming.first.effectiveNotes!,
                      style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                ),
              ] else ...[
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Text('No agenda set.',
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                ),
              ],
            ] else ...[
              // No upcoming — show generate link (matching web)
              const SizedBox(height: 16),
              _sectionLabel('Meetings', cs),
              const SizedBox(height: 6),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text('No upcoming occurrences.',
                            style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                      ),
                      if (_canManage)
                        TextButton(
                          onPressed: _generateOccurrences,
                          child: const Text('Generate schedule'),
                        ),
                    ],
                  ),
                ),
              ),
            ],

            // Upcoming list with inline location editing
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

            // Delete series
            if (_canManage) ...[
              const SizedBox(height: 24),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.delete_outline, color: Colors.red),
                  title: const Text('Delete series',
                      style: TextStyle(color: Colors.red)),
                  onTap: () async {
                    final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        title: const Text('Delete series?'),
                        content: const Text(
                            'This will delete the series and all its occurrences. This cannot be undone.'),
                        actions: [
                          TextButton(
                              onPressed: () => Navigator.pop(ctx, false),
                              child: const Text('Cancel')),
                          TextButton(
                              onPressed: () => Navigator.pop(ctx, true),
                              child: const Text('Delete',
                                  style: TextStyle(color: Colors.red))),
                        ],
                      ),
                    );
                    if (confirmed == true && mounted) {
                      await context
                          .read<ApiService>()
                          .deleteSeries(widget.seriesId);
                      if (mounted) context.pop();
                    }
                  },
                ),
              ),
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
              // status badge hidden – issue #114
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
    final isEditingLoc = _editingLocationOccId == occ.occurrenceId;

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
                  Row(
                    children: [
                      Expanded(
                        child: Text('$dateStr  $timeStr',
                            style: TextStyle(fontSize: 13, color: cs.onSurface)),
                      ),
                      if (occ.host != null) ...[
                        Icon(Icons.person, size: 12, color: cs.primary),
                        const SizedBox(width: 4),
                        Text(occ.host!,
                            style: TextStyle(fontSize: 12, color: cs.primary)),
                      ],
                    ],
                  ),
                  if (isEditingLoc)
                    SizedBox(
                      height: 32,
                      child: TextField(
                        controller: _locationEditCtrl,
                        autofocus: true,
                        style: const TextStyle(fontSize: 12),
                        decoration: const InputDecoration(
                          hintText: 'Location',
                          isDense: true,
                          contentPadding: EdgeInsets.symmetric(
                              horizontal: 8, vertical: 6),
                          border: OutlineInputBorder(),
                        ),
                        onSubmitted: (_) => _saveInlineLocation(occ),
                      ),
                    )
                  else
                    GestureDetector(
                      onTap: _canManage
                          ? () {
                              _locationEditCtrl.text = occ.location ?? '';
                              setState(() =>
                                  _editingLocationOccId = occ.occurrenceId);
                            }
                          : null,
                      child: Text(
                        occ.location ?? (occ.effectiveLocation ?? '—'),
                        style: TextStyle(
                          fontSize: 12,
                          color: cs.onSurfaceVariant,
                          decoration: _canManage
                              ? TextDecoration.underline
                              : null,
                          decorationStyle: TextDecorationStyle.dotted,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, size: 18, color: cs.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}
