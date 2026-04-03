import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class ResourceLinksSection extends StatelessWidget {
  final List<Map<String, String>>? links;
  final bool canEdit;
  final Future<void> Function(List<Map<String, String>> links) onSave;

  const ResourceLinksSection({
    super.key,
    required this.links,
    required this.canEdit,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    final hasLinks = links != null && links!.isNotEmpty;
    if (!hasLinks && !canEdit) return const SizedBox.shrink();

    final cs = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.link, size: 16, color: cs.onSurfaceVariant),
            const SizedBox(width: 8),
            Text('Resources',
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: cs.onSurfaceVariant)),
            const Spacer(),
            if (canEdit)
              TextButton.icon(
                onPressed: () => _showEditDialog(context),
                icon: Icon(hasLinks ? Icons.edit : Icons.add, size: 14),
                label: Text(hasLinks ? 'Edit' : 'Add'),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  textStyle: const TextStyle(fontSize: 12),
                ),
              ),
          ],
        ),
        if (hasLinks)
          Card(
            child: Column(
              children: links!.asMap().entries.map((entry) {
                final i = entry.key;
                final link = entry.value;
                final label = link['label'] ?? '';
                final url = link['url'] ?? '';
                return Column(
                  children: [
                    if (i > 0)
                      Divider(height: 1, indent: 16, endIndent: 16,
                          color: cs.outlineVariant.withValues(alpha: 0.4)),
                    ListTile(
                      dense: true,
                      leading: Icon(Icons.open_in_new, size: 16,
                          color: cs.primary),
                      title: Text(label,
                          style: TextStyle(fontSize: 14, color: cs.primary)),
                      onTap: () => launchUrl(Uri.parse(url)),
                    ),
                  ],
                );
              }).toList(),
            ),
          ),
      ],
    );
  }

  Future<void> _showEditDialog(BuildContext context) async {
    final editLinks = links?.map((l) => Map<String, String>.from(l)).toList()
        ?? [{'label': '', 'url': ''}];

    final result = await showDialog<List<Map<String, String>>>(
      context: context,
      builder: (ctx) => _ResourceLinksEditDialog(initialLinks: editLinks),
    );

    if (result != null) {
      await onSave(result);
    }
  }
}

class _ResourceLinksEditDialog extends StatefulWidget {
  final List<Map<String, String>> initialLinks;

  const _ResourceLinksEditDialog({required this.initialLinks});

  @override
  State<_ResourceLinksEditDialog> createState() =>
      _ResourceLinksEditDialogState();
}

class _ResourceLinksEditDialogState extends State<_ResourceLinksEditDialog> {
  late List<Map<String, String>> _links;

  @override
  void initState() {
    super.initState();
    _links = widget.initialLinks
        .map((l) => Map<String, String>.from(l))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Edit Resources'),
      content: SizedBox(
        width: double.maxFinite,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ..._links.asMap().entries.map((entry) {
                final i = entry.key;
                final link = entry.value;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Column(
                          children: [
                            TextField(
                              decoration:
                                  const InputDecoration(labelText: 'Label'),
                              controller:
                                  TextEditingController(text: link['label']),
                              onChanged: (v) => _links[i]['label'] = v,
                            ),
                            const SizedBox(height: 4),
                            TextField(
                              decoration:
                                  const InputDecoration(labelText: 'URL'),
                              controller:
                                  TextEditingController(text: link['url']),
                              onChanged: (v) => _links[i]['url'] = v,
                              keyboardType: TextInputType.url,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 4),
                      IconButton(
                        icon: const Icon(Icons.close, size: 18),
                        onPressed: () {
                          setState(() => _links.removeAt(i));
                        },
                      ),
                    ],
                  ),
                );
              }),
              TextButton.icon(
                onPressed: () {
                  setState(() => _links.add({'label': '', 'url': ''}));
                },
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Add link'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel')),
        FilledButton(
            onPressed: () {
              final cleaned = _links
                  .where((l) =>
                      (l['label'] ?? '').trim().isNotEmpty &&
                      (l['url'] ?? '').trim().isNotEmpty)
                  .toList();
              Navigator.pop(context, cleaned);
            },
            child: const Text('Save')),
      ],
    );
  }
}
