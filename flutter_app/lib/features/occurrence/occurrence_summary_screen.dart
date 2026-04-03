import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/occurrence.dart';
import '../../models/series.dart';
import '../../services/api_service.dart';

class OccurrenceSummaryScreen extends StatefulWidget {
  final String occurrenceId;
  const OccurrenceSummaryScreen({super.key, required this.occurrenceId});

  @override
  State<OccurrenceSummaryScreen> createState() =>
      _OccurrenceSummaryScreenState();
}

class _OccurrenceSummaryScreenState extends State<OccurrenceSummaryScreen> {
  Occurrence? _occurrence;
  Series? _series;
  bool _loading = true;
  String? _error;
  bool _copied = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<ApiService>();
      final occ = await api.getOccurrence(widget.occurrenceId);
      final series = await api.getSeries(occ.seriesId);
      if (mounted) {
        setState(() {
          _occurrence = occ;
          _series = series;
        });
      }
    } catch (e) {
      debugPrint('ERROR: Failed to load occurrence summary: $e');
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _copyLink() async {
    final link =
        'https://small-group.ai/occurrences/${widget.occurrenceId}/summary';
    await Clipboard.setData(ClipboardData(text: link));
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Meeting Summary')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Meeting Summary')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, style: TextStyle(color: cs.error)),
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
    final effectiveTitle = occ.overrides?.title ?? series.title;
    final effectiveLocation = series.hasLocation
        ? (occ.location ?? occ.overrides?.location ?? series.defaultLocation)
        : (occ.location ?? occ.overrides?.location);
    final effectiveLink = occ.overrides?.onlineLink ?? series.defaultOnlineLink;
    final effectiveNotes = occ.overrides?.notes;
    final duration = occ.overrides?.durationMinutes ?? series.defaultDurationMinutes;
    final isCancelled = occ.status == 'cancelled' || occ.status == 'skipped';

    return Scaffold(
      appBar: AppBar(title: const Text('Meeting Summary')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          if (isCancelled)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              margin: const EdgeInsets.only(bottom: 12),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'This meeting has been ${occ.status}.',
                style: TextStyle(
                    color: Colors.orange.shade800,
                    fontWeight: FontWeight.w500),
                textAlign: TextAlign.center,
              ),
            ),

          // Hero
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Text(effectiveTitle,
                      style: const TextStyle(
                          fontSize: 20, fontWeight: FontWeight.w600),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 8),
                  Text(
                    DateFormat('EEEE, MMMM d, yyyy  h:mm a').format(dt),
                    style: TextStyle(fontSize: 14, color: cs.onSurfaceVariant),
                    textAlign: TextAlign.center,
                  ),
                  if (duration != null) ...[
                    const SizedBox(height: 4),
                    Text('$duration minutes',
                        style: TextStyle(
                            fontSize: 13, color: cs.onSurfaceVariant)),
                  ],
                  const SizedBox(height: 4),
                  Text(series.title,
                      style: TextStyle(
                          fontSize: 13, color: cs.onSurfaceVariant)),
                ],
              ),
            ),
          ),

          // Location & link
          if (effectiveLocation != null || effectiveLink != null) ...[
            const SizedBox(height: 8),
            Card(
              child: Column(
                children: [
                  if (effectiveLink != null)
                    ListTile(
                      leading:
                          Icon(Icons.videocam_outlined, color: cs.primary),
                      title: Text('Join online meeting',
                          style: TextStyle(color: cs.primary)),
                      trailing: Icon(Icons.open_in_new,
                          size: 16, color: cs.onSurfaceVariant),
                      onTap: () => launchUrl(Uri.parse(effectiveLink)),
                    ),
                  if (effectiveLocation != null && effectiveLink != null)
                    Divider(
                        height: 1,
                        indent: 56,
                        color: cs.outlineVariant.withValues(alpha: 0.4)),
                  if (effectiveLocation != null)
                    ListTile(
                      leading: Icon(Icons.location_on_outlined,
                          color: cs.onSurfaceVariant),
                      title: Text(effectiveLocation),
                    ),
                ],
              ),
            ),
          ],

          // Notes
          if (effectiveNotes != null && effectiveNotes.isNotEmpty) ...[
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Notes',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: cs.onSurfaceVariant)),
                    const SizedBox(height: 6),
                    Text(effectiveNotes,
                        style: const TextStyle(fontSize: 14)),
                  ],
                ),
              ),
            ),
          ],

          // Share
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: _copyLink,
            icon: Icon(_copied ? Icons.check : Icons.copy, size: 16),
            label: Text(_copied ? 'Copied!' : 'Copy link'),
            style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(40)),
          ),
        ],
      ),
    );
  }
}
