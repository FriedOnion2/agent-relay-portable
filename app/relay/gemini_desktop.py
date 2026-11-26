"""Read the visible Gemini desktop sidebar and the open chat using Windows UI Automation."""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import ir
from .gemini_apps import AGENT, save_conversations
from .messages import text


# No Chromium profile, credentials or network requests are needed. Only query
# hyperlinks for discovery. Read message text only for an explicit capture.
_READER = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$scope = [System.Windows.Automation.TreeScope]::Descendants
$any = [System.Windows.Automation.Condition]::TrueCondition
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$kind = [System.Windows.Automation.ControlType]
$ae = [System.Windows.Automation.AutomationElement]
$linkCondition = New-Object System.Windows.Automation.PropertyCondition($ae::ControlTypeProperty, $kind::Hyperlink)
$windows = @(Get-Process Gemini -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0)
if ($windows.Count -ne 1) { '{"status":"window","chats":[]}'; exit }
$window = $ae::FromHandle($windows[0].MainWindowHandle)

function Read-Sidebar {
    foreach ($link in $window.FindAll($scope, $linkCondition)) {
        $classes = $link.Current.ClassName -split ' '
        if ($classes -notcontains 'gem-nav-list-item') { continue }
        $value = $null
        if (!$link.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$value)) { continue }
        if ($value.Current.Value -notmatch '^https://gemini\.google\.com/((?:u/\d+/)?app/[a-z0-9_-]+)(?:[?#].*)?$') { continue }
        [PSCustomObject]@{key=$Matches[1]; title=$link.Current.Name; active=($classes -contains 'is-active')}
    }
}

function Read-Text($node) {
    $type = $node.Current.ControlType
    if ($type -eq $kind::Button -or $node.Current.ClassName -match 'cdk-visually-hidden') { return }
    if ($type -eq $kind::Text) { $node.Current.Name; return }
    $child = $walker.GetFirstChild($node)
    if (!$child -and $type -eq $kind::Hyperlink) { $node.Current.Name; return }
    while ($child) {
        Read-Text $child
        $child = $walker.GetNextSibling($child)
    }
}

$chats = @(Read-Sidebar)
$result = @{status='ready'; chats=$chats}
if ($env:RELAY_DESKTOP_CAPTURE) {
    $active = @($chats | Where-Object active)
    if ($active.Count -ne 1 -or $active[0].key -cne $env:RELAY_DESKTOP_CAPTURE) { '{"status":"changed"}'; exit }
    $turns = @(foreach ($node in $window.FindAll($scope, $any)) {
        $classes = $node.Current.ClassName -split ' '
        if ($classes -contains 'user-query-bubble-with-background') { $role = 'user' }
        elseif ($classes -contains 'markdown-main-panel') { $role = 'assistant' }
        else { continue }
        $body = ((Read-Text $node) -join "`n").Trim()
        [PSCustomObject]@{role=$role; text=$body}
    })
    $after = @(Read-Sidebar | Where-Object active)
    if ($after.Count -ne 1 -or $after[0].key -cne $active[0].key) { '{"status":"changed"}'; exit }
    $result.turns = $turns
}
ConvertTo-Json -InputObject $result -Depth 5 -Compress
"""


def _read(key=''):
    if sys.platform != 'win32':
        return {'status': 'unsupported', 'chats': []}
    shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = base64.b64encode(_READER.encode('utf-16-le')).decode('ascii')
    try:
        result = subprocess.run([str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', script],
                                env=dict(os.environ, RELAY_DESKTOP_CAPTURE=key), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=40, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError(text('err.gemini_desktop_read')) from None


def recent():
    return dict(ok=True, **_read())


def import_open(key):
    if not isinstance(key, str) or not re.fullmatch(r'(?:u/\d+/)?app/[a-zA-Z0-9_-]{1,128}', key):
        raise ValueError(text('err.gemini_desktop_changed'))
    snapshot = _read(key)
    active = [chat for chat in snapshot.get('chats', []) if chat['active']]
    if snapshot['status'] != 'ready' or len(active) != 1 or active[0]['key'] != key:
        raise ValueError(text('err.gemini_desktop_changed'))
    rows = snapshot.get('turns', [])
    if not rows or len(rows) % 2 or any(row['role'] != (ir.ASSISTANT if i % 2 else ir.USER)
                                        or not row['text'].strip() for i, row in enumerate(rows)):
        raise ValueError(text('err.gemini_desktop_incomplete'))
    turns = [ir.Turn(row['role'], [ir.Block.text_block(row['text'])]) for row in rows]
    fingerprint = json.dumps([key, rows], ensure_ascii=False, sort_keys=True).encode('utf-8')
    conv = ir.Conversation(source=AGENT, id='desktop-' + hashlib.sha256(fingerprint).hexdigest(),
                           title=active[0]['title'], turns=turns)
    return save_conversations([conv])
