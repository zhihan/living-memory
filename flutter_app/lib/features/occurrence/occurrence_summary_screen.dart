import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';

class OccurrenceSummaryScreen extends StatefulWidget {
  final String occurrenceId;
  final String? inviteId;
  const OccurrenceSummaryScreen({
    super.key,
    required this.occurrenceId,
    this.inviteId,
  });

  @override
  State<OccurrenceSummaryScreen> createState() =>
      _OccurrenceSummaryScreenState();
}

class _OccurrenceSummaryScreenState extends State<OccurrenceSummaryScreen> {
  Map<String, dynamic>? _summary;
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
      final data = await api.getPublicOccurrenceSummary(widget.occurrenceId);
      if (mounted) setState(() => _summary = data);
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

    final data = _summary!;
    final scheduledFor = data['scheduled_for'] as String;
    final dt = DateTime.parse(scheduledFor).toLocal();
    final status = data['status'] as String? ?? 'scheduled';
    final overrides = data['overrides'] as Map<String, dynamic>?;
    final seriesTitle = data['series_title'] as String? ?? 'Meeting';

    final effectiveTitle = overrides?['title'] as String? ?? seriesTitle;
    final effectiveLocation = (data['location'] as String?) ??
        (overrides?['location'] as String?) ??
        (data['default_location'] as String?);
    final effectiveLink = (overrides?['online_link'] as String?) ??
        (data['default_online_link'] as String?);
    final effectiveNotes = overrides?['notes'] as String?;
    final duration = (overrides?['duration_minutes'] as num?)?.toInt() ??
        (data['default_duration_minutes'] as num?)?.toInt();

    final isCancelled = status == 'cancelled' || status == 'skipped';

    final inviteUrl = widget.inviteId != null
        ? 'https://small-group.ai/invites/${widget.inviteId}'
        : null;

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
                'This meeting has been $status.',
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
                  Text(seriesTitle,
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

          // Invite / QR code
          if (inviteUrl != null) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    Text('Join this group',
                        style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: cs.onSurfaceVariant)),
                    const SizedBox(height: 12),
                    QrImageView(
                      data: inviteUrl,
                      version: QrVersions.auto,
                      size: 160,
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: () => context.push('/invites/${widget.inviteId}'),
                      child: const Text('Join this group'),
                    ),
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
