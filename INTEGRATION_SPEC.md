# Integration Spec — New GUI Components

This document describes how to integrate the 8 new component modules into `corridorkey_gui.py`.

## Components

1. **preview_panel.py** — Live preview panel showing the current frame/output with before/after toggle
2. **console_panel.py** — Collapsible console log panel that captures logging output
3. **weight_detector.py** — Automatic weight file detection with status indicator
4. **presets_manager.py** — Save/load inference parameter presets
5. **drop_handler.py** — Enhanced drag-and-drop with visual feedback and multi-file support
6. **notifications.py** — Toast-style notification system for status updates
7. **thumbnails.py** — Thumbnail generator for clip list rows
8. **output_config.py** — Extended output configuration panel (resolution, codec, etc.)

## Integration Points

### Imports
Add imports for all 8 modules after the existing import block at the top of `corridorkey_gui.py`.

### Layout Changes
- The main content area (row 4) should use a `tk.PanedWindow` to split between the clip list (left) and preview panel (right)
- The settings panel stays in the right sidebar but adds a presets section at the top
- A collapsible console panel is added below the main content area (between content and bottom bar)

### Component Wiring

#### PreviewPanel
- Instantiated in the content area, right side of the PanedWindow
- Connected to clip selection — when a clip row is clicked, preview updates
- Receives output frames after inference completes

#### ConsolePanel
- Instantiated between the content area and the bottom bar
- Captures Python logging output via a custom handler
- Has a toggle button in the top bar to show/hide

#### WeightDetector
- Replaces the manual `_weights_exist()` / `_weights_path()` checks
- Provides a status indicator in the top bar
- Emits callbacks when weights are found/missing

#### PresetsManager
- Added to the top of the settings panel
- Save/Load buttons with a dropdown of named presets
- Reads/writes JSON preset files to a `presets/` directory

#### DropHandler
- Enhances the existing drop zone with visual feedback (highlight on drag-over)
- Supports dropping multiple files/folders at once
- Shows a drop overlay with file count

#### Notifications
- Toast notifications appear in the top-right corner
- Used for: inference complete, errors, weight download status
- Auto-dismiss after 5 seconds

#### Thumbnails
- Generates thumbnail images for clip rows
- Displayed as a small preview in the ClipRow badge area
- Cached to disk in a `.thumbnails/` directory

#### OutputConfig
- Extends the existing output format section in SettingsPanel
- Adds resolution presets, codec selection, and quality slider
- Replaces the simple format toggles with a more detailed panel
