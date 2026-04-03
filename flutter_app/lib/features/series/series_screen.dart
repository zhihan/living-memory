import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:provider/provider.dart';

import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../models/room.dart';
import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import '../../shared/formatting/timezone_helpers.dart';
import '../../shared/widgets/check_in_report.dart';
import '../../shared/widgets/resource_links.dart';

class SeriesScreen extends StatefulWidget {
  final String seriesId;
  const SeriesScreen({super.key, required this.seriesId});

  @override
  State<SeriesScreen> createState() => _SeriesScreenState();
}

class _SeriesScreenState extends State<SeriesScreen> {
  Series? _series;
  Room? _room;
  List<Occurrence>? _occurrences;
  bool _loading = true;
  String? _error;
  String _deviceTz = 'UTC';

  // Inline location editing
  String? _editingLocationOccId;
  final _locationEditCtrl = TextEditingController();


  @override
  void initState() {
    super.initState();
    _loadDeviceTz();
    _load();
  }

  Future<void> _loadDeviceTz() async {
    final tz = await getDeviceTimezone();
    if (mounted) setState(() => _deviceTz = tz);
  }

  @override
  void dispose() {
    _locationEditCtrl.dispose();
    super.dispose();
  }

  String get _uid => context.read<AuthService>().currentUser!.uid;

  bool get _canManage {
    final room = _room;
    if (room == null) return false;
    final role = room.memberRoles[_uid];
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
        api.getRoom(series.roomId),
        api.listSeriesOccurrences(widget.seriesId),
      ]);
      if (mounted) {
        setState(() {
          _series = series;
          _room = results[0] as Room;
          _occurrences = results[1] as List<Occurrence>;
        });
      }
    } catch (e) {
      debugPrint('ERROR: Failed to load series: $e');
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
      debugPrint('ERROR: Failed to generate occurrences: $e');
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
      debugPrint('ERROR: Failed to save inline location: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }


  Future<void> _addOccurrence() async {
    final series = _series;
    final room = _room;
    if (series == null || room == null) return;

    final pickedDate = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (pickedDate == null || !mounted) return;

    // Default to series time, let user override
    final defaultTime = series.defaultTime;
    TimeOfDay initialTime;
    if (defaultTime != null && defaultTime.contains(':')) {
      final parts = defaultTime.split(':');
      initialTime = TimeOfDay(
          hour: int.tryParse(parts[0]) ?? 0,
          minute: int.tryParse(parts[1]) ?? 0);
    } else {
      initialTime = const TimeOfDay(hour: 9, minute: 0);
    }

    final pickedTime = await showTimePicker(
      context: context,
      initialTime: initialTime,
    );
    if (pickedTime == null || !mounted) return;

    // Build local datetime and convert to UTC using room timezone
    final localDt = DateTime(
      pickedDate.year, pickedDate.month, pickedDate.day,
      pickedTime.hour, pickedTime.minute,
    );
    // Simple UTC conversion — the backend accepts ISO 8601 UTC strings
    final scheduledFor = localDt.toUtc().toIso8601String();

    try {
      await context.read<ApiService>().createOccurrence(
        series.seriesId,
        scheduledFor,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Occurrence added for ${DateFormat('E, MMM d').format(pickedDate)}')),
        );
        _load();
      }
    } catch (e) {
      debugPrint('ERROR: Failed to add occurrence: $e');
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
    final timeCtrl = TextEditingController(text: series.defaultTime ?? '');
    final durationCtrl = TextEditingController(
        text: series.defaultDurationMinutes?.toString() ?? '');
    final locationCtrl =
        TextEditingController(text: series.defaultLocation ?? '');
    final linkCtrl =
        TextEditingController(text: series.defaultOnlineLink ?? '');
    var locationType = series.locationType;
    var enableDone = series.enableDone;
    String? extendDate;
    var hostRotationMode = series.hostRotationMode;
    var hostRotation = List<String>.from(series.hostRotation ?? []);
    var hostAddresses = Map<String, String>.from(series.hostAddresses ?? {});
    var editFreq = series.scheduleRule.frequency;
    var editWeekdays = List<int>.from(series.scheduleRule.weekdays);
    final origFreq = series.scheduleRule.frequency;
    final origWeekdays = List<int>.from(series.scheduleRule.weekdays);
    const weekdayLabels = {
      1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu',
      5: 'Fri', 6: 'Sat', 7: 'Sun',
    };

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
                  DropdownButtonFormField<String>(
                    value: editFreq,
                    decoration: const InputDecoration(labelText: 'Frequency'),
                    items: const [
                      DropdownMenuItem(value: 'daily', child: Text('Daily')),
                      DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                      DropdownMenuItem(value: 'weekdays', child: Text('Weekdays')),
                      DropdownMenuItem(value: 'once', child: Text('One-time')),
                    ],
                    onChanged: (v) => setDialogState(() => editFreq = v!),
                  ),
                  if (editFreq == 'weekly') ...[
                    const SizedBox(height: 12),
                    const Text('Weekdays'),
                    Wrap(
                      spacing: 4,
                      children: weekdayLabels.entries.map((e) {
                        return FilterChip(
                          label: Text(e.value),
                          selected: editWeekdays.contains(e.key),
                          onSelected: (sel) {
                            setDialogState(() {
                              if (sel) {
                                editWeekdays.add(e.key);
                              } else {
                                editWeekdays.remove(e.key);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                  ],
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
                  if (hostRotationMode == 'host_and_location') ...[
                    InputDecorator(
                      decoration:
                          const InputDecoration(labelText: 'Location Type'),
                      child: Text('Locations are set per host below.',
                          style: TextStyle(
                              fontSize: 13,
                              color: Theme.of(ctx)
                                  .colorScheme
                                  .onSurfaceVariant)),
                    ),
                  ] else ...[
                    DropdownButtonFormField<String>(
                      initialValue: locationType,
                      decoration:
                          const InputDecoration(labelText: 'Location Type'),
                      items: const [
                        DropdownMenuItem(
                            value: 'none', child: Text('None')),
                        DropdownMenuItem(
                            value: 'fixed', child: Text('Fixed')),
                        DropdownMenuItem(
                            value: 'per_occurrence',
                            child: Text('Per Meeting')),
                      ],
                      onChanged: (v) =>
                          setDialogState(() {
                            locationType = v!;
                            if (locationType == 'none' && hostRotationMode == 'host_and_location') {
                              hostRotationMode = 'host_only';
                            }
                          }),
                    ),
                    if (locationType == 'fixed') ...[
                      const SizedBox(height: 12),
                      TextField(
                          controller: locationCtrl,
                          decoration:
                              const InputDecoration(labelText: 'Location')),
                    ],
                  ],
                  const SizedBox(height: 12),
                  TextField(
                      controller: linkCtrl,
                      decoration:
                          const InputDecoration(labelText: 'Online Link')),
                  SwitchListTile(
                    title: const Text('Show "Done" button'),
                    value: enableDone,
                    onChanged: (v) => setDialogState(() => enableDone = v),
                    contentPadding: EdgeInsets.zero,
                  ),
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
                    items: [
                      const DropdownMenuItem(value: 'none', child: Text('No host')),
                      const DropdownMenuItem(value: 'manual', child: Text('Manual')),
                      const DropdownMenuItem(value: 'host_only', child: Text('Rotating hosts')),
                      if (locationType != 'none')
                        const DropdownMenuItem(value: 'host_and_location', child: Text('Rotate host + location')),
                    ],
                    onChanged: (v) => setDialogState(() => hostRotationMode = v!),
                  ),
                  if (hostRotationMode != 'none' && hostRotationMode != 'manual') ...[
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
                onPressed: () async {
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
                  if (enableDone != series.enableDone) {
                    updates['enable_done'] = enableDone;
                  }
                  if (hostRotationMode != series.hostRotationMode) {
                    updates['rotation_mode'] = hostRotationMode;
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

                  // Check if schedule changed
                  final sortedEditWeekdays = List<int>.from(editWeekdays)..sort();
                  final sortedOrigWeekdays = List<int>.from(origWeekdays)..sort();
                  final scheduleChanged = editFreq != origFreq ||
                      sortedEditWeekdays.length != sortedOrigWeekdays.length ||
                      !List.generate(sortedEditWeekdays.length,
                          (i) => sortedEditWeekdays[i] == sortedOrigWeekdays[i])
                          .every((eq) => eq);

                  if (scheduleChanged) {
                    final chosenMode = await showDialog<String>(
                      context: ctx,
                      builder: (dialogCtx) => AlertDialog(
                        title: const Text('Schedule changed'),
                        content: const Text(
                            'The frequency or weekdays have changed. How should existing occurrences be handled?'),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(dialogCtx),
                            child: const Text('Cancel'),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(dialogCtx, 'regenerate'),
                            child: const Text('Delete future & regenerate'),
                          ),
                          FilledButton(
                            onPressed: () => Navigator.pop(dialogCtx, 'adjust'),
                            child: const Text('Adjust schedule'),
                          ),
                        ],
                      ),
                    );
                    if (chosenMode == null) return; // user cancelled
                    updates['schedule_rule'] = {
                      'frequency': editFreq,
                      if (editFreq == 'weekly') 'weekdays': sortedEditWeekdays,
                      'interval': 1,
                    };
                    updates['schedule_mode'] = chosenMode;
                  }

                  Navigator.pop(
                      ctx, updates.isEmpty && extendDate == null ? null : updates);
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
      debugPrint('ERROR: Failed to update series: $e');
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
      floatingActionButton: _canManage
          ? FloatingActionButton.small(
              onPressed: _addOccurrence,
              tooltip: 'Add occurrence',
              child: const Icon(Icons.add),
            )
          : null,
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
                    if (series.hasLocation && series.defaultLocation != null)
                      _infoRow(Icons.location_on_outlined, series.defaultLocation!, cs),
                    if (series.defaultOnlineLink != null)
                      _infoRow(Icons.link, series.defaultOnlineLink!, cs),
                    if (series.description != null &&
                        series.description!.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      MarkdownBody(
                        data: series.description!,
                        softLineBreak: true,
                        onTapLink: (text, href, title) {
                          if (href != null) launchUrl(Uri.parse(href));
                        },
                      ),
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

            // Next meeting
            if (upcoming.isNotEmpty) ...[
              const SizedBox(height: 16),
              _sectionLabel('Next Meeting', cs),
              const SizedBox(height: 6),
              _meetingCard(upcoming.first, cs, isNext: true),
              if (upcoming.first.effectiveNotes != null) ...[
                const SizedBox(height: 4),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: MarkdownBody(
                    data: upcoming.first.effectiveNotes!,
                    softLineBreak: true,
                    onTapLink: (text, href, title) {
                      if (href != null) launchUrl(Uri.parse(href));
                    },
                  ),
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

            // Past history
            if (past.length > 1) ...[
              const SizedBox(height: 16),
              _sectionLabel('Recent', cs),
              const SizedBox(height: 6),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: past.skip(1).take(6).toList().asMap().entries.map((entry) {
                    final occ = entry.value;
                    final isLast = entry.key == (past.length - 2).clamp(0, 5);
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

            // Upcoming list with inline location editing
            if (upcoming.length > 1) ...[
              const SizedBox(height: 16),
              _sectionLabel('Upcoming', cs),
              const SizedBox(height: 6),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: upcoming.skip(1).take(6).toList().asMap().entries.map((entry) {
                    final occ = entry.value;
                    final isLast = entry.key == (upcoming.length - 2).clamp(0, 5);
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

            // Resources (below upcoming)
            const SizedBox(height: 12),
            ResourceLinksSection(
              links: series.links,
              canEdit: _canManage,
              onSave: (links) async {
                await context.read<ApiService>().updateSeries(
                    widget.seriesId, {'links': links});
                _load();
              },
            ),

            // Completion report — only when Done is enabled
            if (_canManage && series.enableDone) ...[
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

  String _occurrencePath(String id) => '/occurrences/$id';

  Widget _meetingCard(Occurrence occ, ColorScheme cs,
      {bool isNext = false, bool isPast = false}) {
    final dt = occ.scheduledDateTime.toLocal();
    final dateStr = DateFormat('E, MMM d').format(dt);
    final roomTz = _room?.timezone ?? _deviceTz;
    final showDualTz = !timezonesMatch(roomTz, _deviceTz);
    final timeStr = showDualTz
        ? '${DateFormat('HH:mm').format(dt)} (${dt.timeZoneName})'
        : DateFormat('HH:mm').format(dt);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push(_occurrencePath(occ.occurrenceId)),
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
                    if (_series?.hostRotationMode != 'none' &&
                        occ.host != null) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Icon(Icons.person, size: 12, color: cs.primary),
                          const SizedBox(width: 3),
                          Expanded(
                            child: Text(
                                occ.effectiveLocation != null
                                    ? '${occ.host!} · ${occ.effectiveLocation!}'
                                    : occ.host!,
                                style: TextStyle(fontSize: 12, color: cs.primary),
                                overflow: TextOverflow.ellipsis),
                          ),
                        ],
                      ),
                    ] else if (occ.effectiveLocation != null && (_series?.hasLocation != false || occ.location != null)) ...[
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
              if (isNext && _canManage)
                IconButton(
                  icon: Icon(Icons.edit_outlined, size: 20, color: cs.onSurfaceVariant),
                  onPressed: () => _showEditOccurrenceDialog(occ),
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showEditOccurrenceDialog(Occurrence occ) async {
    final rotationMode = _series?.hostRotationMode ?? 'none';
    final showHost = rotationMode == 'host_only' || rotationMode == 'host_and_location' || rotationMode == 'manual';
    final showLocation = rotationMode == 'none' || rotationMode == 'per_occurrence' || rotationMode == 'host_and_location';

    final hostCtrl = TextEditingController(text: occ.host ?? '');
    final locCtrl = TextEditingController(text: occ.location ?? '');
    final dt = occ.scheduledDateTime.toLocal();
    final title = DateFormat('E, MMM d').format(dt);

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (showHost)
              TextField(
                controller: hostCtrl,
                decoration: const InputDecoration(labelText: 'Host'),
              ),
            if (showHost && showLocation) const SizedBox(height: 12),
            if (showLocation)
              TextField(
                controller: locCtrl,
                decoration: const InputDecoration(labelText: 'Location'),
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final updates = <String, dynamic>{};
              if (showHost) {
                final h = hostCtrl.text.trim();
                updates['host'] = h.isNotEmpty ? h : null;
              }
              if (showLocation) {
                final l = locCtrl.text.trim();
                updates['location'] = l.isNotEmpty ? l : null;
              }
              Navigator.pop(ctx, updates);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (result == null || result.isEmpty) return;
    try {
      await context.read<ApiService>().updateOccurrence(
          occ.occurrenceId, result);
      _load();
    } catch (e) {
      debugPrint('ERROR: Failed to update occurrence: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Widget _occurrenceListItem(Occurrence occ, ColorScheme cs) {
    final dt = occ.scheduledDateTime.toLocal();
    final dateStr = DateFormat('E, MMM d').format(dt);
    final roomTz = _room?.timezone ?? _deviceTz;
    final showDualTz = !timezonesMatch(roomTz, _deviceTz);
    final timeStr = showDualTz
        ? '${DateFormat('HH:mm').format(dt)} (${dt.timeZoneName})'
        : DateFormat('HH:mm').format(dt);
    final isEditingLoc = _editingLocationOccId == occ.occurrenceId;

    return InkWell(
      onTap: () => context.push(_occurrencePath(occ.occurrenceId)),
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
                      if (occ.host != null &&
                          _series?.hostRotationMode != 'none' &&
                          _series?.hostRotationMode != 'host_and_location') ...[
                        Icon(Icons.person, size: 12, color: cs.primary),
                        const SizedBox(width: 4),
                        Text(occ.host!,
                            style: TextStyle(fontSize: 12, color: cs.primary)),
                      ],
                    ],
                  ),
                  // In host+location mode, show host and location as paired unit
                  if (_series?.hostRotationMode == 'host_and_location' &&
                      occ.host != null)
                    Row(
                      children: [
                        Icon(Icons.person, size: 12, color: cs.primary),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            occ.effectiveLocation != null
                                ? '${occ.host!} · ${occ.effectiveLocation!}'
                                : occ.host!,
                            style: TextStyle(fontSize: 12, color: cs.primary),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    )
                  else if (_series?.hasLocation == false && occ.location == null)
                    const SizedBox.shrink()
                  else if (_series?.hasLocation == false && occ.location != null)
                    Text(
                      occ.location!,
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                      overflow: TextOverflow.ellipsis,
                    )
                  else if (isEditingLoc)
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
            if (_canManage)
              IconButton(
                icon: Icon(Icons.edit_outlined, size: 20, color: cs.onSurfaceVariant),
                onPressed: () => _showEditOccurrenceDialog(occ),
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              )
            else
              Icon(Icons.chevron_right, size: 18, color: cs.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}
