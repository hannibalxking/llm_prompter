# promptbuilder/ui/widgets/diff_apply_tab/diff_action_handler.py
from collections import defaultdict
from typing import TYPE_CHECKING, List, Dict, Tuple
from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QApplication
from loguru import logger

from ....core import (
    apply_hunks, ApplyReport, DiffBase, DiffHunk, DiffSuggestion,
    PatchApplyError, apply_suggestion as legacy_apply_suggestion
)
from ....ui.windows.main_window import MainWindow


if TYPE_CHECKING:
    from .diff_apply_widget import DiffApplyWidget


class DiffActionHandler:
    """Handles the logic for applying and rejecting diff suggestions/hunks."""

    def __init__(self, widget: 'DiffApplyWidget'):
        """Initializes the handler."""
        self.widget = widget
        self.main_window: MainWindow | None = None
        parent = self.widget
        while parent is not None:
            if isinstance(parent, MainWindow):
                self.main_window = parent
                break
            parent = parent.parent()
        if self.main_window is None:
             active_window = QApplication.instance().activeWindow() if QApplication.instance() else None
             if isinstance(active_window, MainWindow):
                 self.main_window = active_window
                 logger.warning("Using QApplication.activeWindow() as fallback for MainWindow reference in DiffActionHandler.")
             else:
                 logger.warning("Could not get MainWindow reference in DiffActionHandler. Config access might fail.")

    def _get_config_max_distance(self) -> float:
        """Safely retrieves the max distance setting from the config."""
        default_distance = 0.05
        try:
            if self.main_window and hasattr(self.main_window, 'config'):
                # Ensure config object is accessed correctly
                config_obj = getattr(self.main_window, 'config', None)
                if config_obj:
                    return getattr(config_obj, 'diff_matcher_max_distance', default_distance)
                else:
                     logger.warning("MainWindow found but config attribute missing.")
                     return default_distance
            else:
                logger.warning("Could not access MainWindow or its config to get max_distance. Using default.")
                return default_distance
        except Exception as e:
            logger.exception(f"Unexpected error getting config max distance: {e}")
            return default_distance

    def accept_current(self):
        """Applies the currently selected diff suggestion or hunk(s) for the selected file."""
        current_selection = self.widget._current_suggestion
        project_root = self.widget._project_root
        if not current_selection or not project_root:
            logger.warning("Accept clicked but no suggestion selected or project root missing.")
            return

        target_path = current_selection.path
        suggestions_for_file = self.widget._suggestions.get(target_path, [])
        if not suggestions_for_file:
             logger.error(f"Internal inconsistency: Current selection path {target_path} not found in suggestions dict.")
             return

        logger.info(f"Attempting to accept and apply suggestion(s) for: {current_selection.rel_path}")

        is_all_hunks = all(isinstance(s, DiffHunk) for s in suggestions_for_file)
        is_all_legacy = all(isinstance(s, DiffSuggestion) for s in suggestions_for_file)

        if not is_all_hunks and not is_all_legacy:
             msg = f"Cannot apply changes for {current_selection.rel_path}: Mixed suggestion types (legacy and new format) found for the same file. Please clear and re-parse."
             logger.error(msg)
             QMessageBox.critical(self.widget, "Apply Error", msg)
             return

        first_suggestion = suggestions_for_file[0]

        if isinstance(first_suggestion, DiffHunk):
            # Apply ALL matched hunks for this file
            hunks_to_apply = [h for h in suggestions_for_file if isinstance(h, DiffHunk) and h.status == 'matched']
            if not hunks_to_apply:
                msg = f"Cannot apply changes for {first_suggestion.rel_path}: No matched hunks found for this file."
                logger.error(msg)
                QMessageBox.warning(self.widget, "Apply Error", msg)
                return
            is_new_file = not target_path.exists()
            action_desc = "Create new file at" if is_new_file else f"Apply {len(hunks_to_apply)} change(s) to"
            backup_note = "" if is_new_file else "\nA backup will be created/overwritten in the 'backups' folder."
            reply = QMessageBox.question(self.widget, "Confirm Apply",
                                         f"{action_desc}:\n{first_suggestion.rel_path}?{backup_note}",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                logger.info("User cancelled apply operation.")
                return
            try:
                config_max_distance = self._get_config_max_distance()
                report = apply_hunks(target_path, hunks_to_apply, project_root, config_max_distance)
                self._process_apply_report(report, suggestions_for_file)
            except Exception as e:
                logger.exception(f"Unexpected error calling apply_hunks for {first_suggestion.rel_path}: {e}")
                QMessageBox.critical(self.widget, "Apply Error", f"An unexpected error occurred applying changes:\n{e}")

        elif isinstance(first_suggestion, DiffSuggestion):
            # Apply only the currently selected legacy suggestion
            legacy_suggestion = current_selection
            if not isinstance(legacy_suggestion, DiffSuggestion):
                 logger.error(f"Type mismatch during legacy apply for {target_path}")
                 return
            logger.warning(f"Applying legacy DiffSuggestion for {legacy_suggestion.rel_path}.")
            if legacy_suggestion.proposed_content is None:
                logger.error(f"Cannot apply legacy change for {legacy_suggestion.rel_path}: Missing proposed_content.")
                QMessageBox.critical(self.widget, "Apply Error", f"Cannot apply legacy changes for:\n{legacy_suggestion.rel_path}\n\nLLM did not provide the full proposed file content.")
                return
            is_new_file = not target_path.exists()
            action_desc = "Create new file at" if is_new_file else "Apply changes to"
            backup_note = "" if is_new_file else "\nA backup will be created/overwritten in the 'backups' folder."
            reply = QMessageBox.question(self.widget, "Confirm Apply (Legacy)",
                                         f"{action_desc}:\n{legacy_suggestion.rel_path}?{backup_note}",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                logger.info("User cancelled legacy apply operation.")
                return

            if PatchApplyError:
                _legacy_exceptions: Tuple[type[Exception], ...] = (PatchApplyError, FileNotFoundError, ImportError, Exception)
            else:
                _legacy_exceptions = (FileNotFoundError, ImportError, Exception)

            try:
                if legacy_apply_suggestion is None:
                    raise ImportError("Legacy patcher function is unavailable.")
                status, message = legacy_apply_suggestion(legacy_suggestion, project_root)
                legacy_suggestion.status = 'accepted'

                if target_path in self.widget._suggestions:
                    self.widget._suggestions[target_path] = [s for s in self.widget._suggestions[target_path] if s != legacy_suggestion]
                    if not self.widget._suggestions[target_path]:
                        del self.widget._suggestions[target_path]

                self.widget.list_manager.update_list()

                if status == "applied_ok":
                    logger.info(f"Successfully applied legacy suggestion for: {legacy_suggestion.rel_path}. {message or ''}")
                    QMessageBox.information(self.widget, "Success", f"Legacy changes applied successfully to:\n{legacy_suggestion.rel_path}\n\n{message or ''}")
                elif status == "applied_with_discrepancies":
                    logger.warning(f"Applied legacy suggestion for {legacy_suggestion.rel_path} with discrepancies: {message}")
                    QMessageBox.warning(self.widget, "Applied with Discrepancies", f"Legacy changes applied to:\n{legacy_suggestion.rel_path}\n\nWarning: {message}")
                else:
                     logger.error(f"Unknown status returned from legacy apply_suggestion: {status}")
                     QMessageBox.critical(self.widget, "Error", f"An unknown error occurred applying legacy changes to:\n{legacy_suggestion.rel_path}")

            except _legacy_exceptions as e:
                logger.exception(f"Failed to apply legacy suggestion for {legacy_suggestion.rel_path}: {e}")
                error_message = f"Failed to apply legacy changes to:\n{legacy_suggestion.rel_path}\n\nError: {e}"
                QMessageBox.critical(self.widget, "Apply Error", error_message)
        else:
            logger.error(f"Unknown suggestion type encountered: {type(first_suggestion)}")
            QMessageBox.critical(self.widget, "Error", "Cannot apply unknown suggestion type.")

    def reject_current(self):
        """Rejects the currently selected diff suggestion or all suggestions for the selected file path."""
        current_selection = self.widget._current_suggestion
        if not current_selection:
            logger.warning("Reject clicked but no suggestion selected.")
            return
        target_path = current_selection.path
        suggestions_for_file = self.widget._suggestions.get(target_path, [])
        if not suggestions_for_file:
            logger.error(f"Internal inconsistency: Current selection path {target_path} not found in suggestions dict for reject.")
            return
        logger.info(f"Rejecting suggestion(s) for file: {current_selection.rel_path}")
        # Mark all suggestions for this path as rejected before removing
        for suggestion in suggestions_for_file:
            suggestion.status = 'rejected'
        if target_path in self.widget._suggestions:
            del self.widget._suggestions[target_path]
        self.widget.list_manager.update_list()
        self.widget._clear_diff_view() # Clear preview after rejecting

    def apply_all(self):
        """Applies all pending and matched suggestions/hunks."""
        project_root = self.widget._project_root
        if not project_root:
            QMessageBox.warning(self.widget, "Error", "Project root not set.")
            return

        applicable_hunks_by_file: Dict[Path, List[DiffHunk]] = {}
        applicable_legacy: List[DiffSuggestion] = []
        all_suggestions_flat = [s for sublist in self.widget._suggestions.values() for s in sublist]

        paths_with_mixed_types = set()
        temp_types: Dict[Path, type] = {}
        for s in all_suggestions_flat:
            if s.path in paths_with_mixed_types: continue
            current_type = type(s)
            if s.path not in temp_types:
                temp_types[s.path] = current_type
            elif temp_types[s.path] != current_type:
                paths_with_mixed_types.add(s.path)

        if paths_with_mixed_types:
             file_list = "\n - ".join([p.name for p in paths_with_mixed_types])
             msg = f"Cannot Apply All: Mixed suggestion types (legacy and new format) found for the following file(s):\n - {file_list}\nPlease clear and re-parse with a consistent format."
             logger.error(msg)
             QMessageBox.critical(self.widget, "Apply Error", msg)
             return

        for suggestion in all_suggestions_flat:
            if isinstance(suggestion, DiffHunk) and suggestion.status == 'matched':
                applicable_hunks_by_file.setdefault(suggestion.path, []).append(suggestion)
            elif isinstance(suggestion, DiffSuggestion) and suggestion.status == 'pending' and suggestion.proposed_content is not None:
                 applicable_legacy.append(suggestion)

        total_applicable_files = len(applicable_hunks_by_file) + len(applicable_legacy)
        total_applicable_hunks = sum(len(h_list) for h_list in applicable_hunks_by_file.values())

        if not total_applicable_files:
            QMessageBox.information(self.widget, "Apply All", "No applicable changes found to apply.")
            return

        reply = QMessageBox.question(self.widget, "Confirm Apply All",
                                     f"Apply all applicable changes?\n\n"
                                     f"- {total_applicable_hunks} new hunk(s) across {len(applicable_hunks_by_file)} file(s)\n"
                                     f"- {len(applicable_legacy)} legacy suggestion(s)\n\n"
                                     "Backups will be created/overwritten for modified files.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Cancel:
            return

        logger.info(f"Applying all {total_applicable_hunks + len(applicable_legacy)} applicable suggestions across {total_applicable_files} files.")
        applied_files_count = 0
        total_lines_applied_all = 0
        processed_reports: List[ApplyReport] = []
        processed_legacy_paths: List[Path] = []
        failed_legacy_files: List[str] = []

        config_max_distance = self._get_config_max_distance()
        for file_path, hunks_for_file in applicable_hunks_by_file.items():
            try:
                report = apply_hunks(file_path, hunks_for_file, project_root, config_max_distance)
                processed_reports.append(report)
                if report.is_successful():
                    applied_files_count += 1
                    if report.lines_applied is not None:
                         total_lines_applied_all += report.lines_applied
            except Exception as e:
                 logger.exception(f"Unexpected error calling apply_hunks for {file_path.name} during Apply All: {e}")
                 processed_reports.append(ApplyReport(file_path=file_path, status="failed_write", message=f"Unexpected error: {e}"))

        if applicable_legacy:
            logger.warning(f"Processing {len(applicable_legacy)} legacy suggestions during Apply All.")
            if PatchApplyError: _legacy_exceptions = (PatchApplyError, FileNotFoundError, ImportError, Exception)
            else: _legacy_exceptions = (FileNotFoundError, ImportError, Exception)

            if legacy_apply_suggestion is None:
                logger.error("Cannot process legacy suggestions: Legacy patcher function is unavailable.")
                failed_legacy_files.extend([f"{s.rel_path} (Patcher Unavailable)" for s in applicable_legacy])
            else:
                for suggestion in applicable_legacy:
                    try:
                        status, message = legacy_apply_suggestion(suggestion, project_root)
                        if status == "applied_ok" or status == "applied_with_discrepancies":
                            suggestion.status = 'accepted'
                            processed_legacy_paths.append(suggestion.path)
                            applied_files_count += 1
                            total_lines_applied_all += (suggestion.lines_added + suggestion.lines_deleted)
                            if status == "applied_with_discrepancies":
                                 processed_reports.append(ApplyReport(file_path=suggestion.path, status="ok", message=f"Legacy apply had discrepancies: {message}"))
                        else:
                            failed_legacy_files.append(f"{suggestion.rel_path} (Legacy Apply Error: {status})")
                    except _legacy_exceptions as e:
                        logger.exception(f"Failed to apply legacy suggestion for {suggestion.rel_path} during Apply All: {e}")
                        failed_legacy_files.append(f"{suggestion.rel_path} ({type(e).__name__})")

        successful_paths = {r.file_path for r in processed_reports if r.is_successful()} | set(processed_legacy_paths)
        original_suggestion_count = sum(len(v) for v in self.widget._suggestions.values())

        new_suggestions_dict = defaultdict(list)
        for path, s_list in self.widget._suggestions.items():
            if path not in successful_paths:
                new_suggestions_dict[path] = s_list
            else:
                 # Keep only suggestions that were *not* successfully applied
                 filtered_list = [s for s in s_list if s.status != 'accepted']
                 if filtered_list:
                     new_suggestions_dict[path] = filtered_list
        self.widget._suggestions = new_suggestions_dict

        final_suggestion_count = sum(len(v) for v in self.widget._suggestions.values())
        removed_count = original_suggestion_count - final_suggestion_count
        logger.info(f"Removed {removed_count} successfully applied suggestions from internal state.")
        self.widget.list_manager.update_list()

        summary_lines = [f"Applied changes for {applied_files_count} out of {total_applicable_files} applicable files ({total_lines_applied_all} lines affected)."]
        skipped_unmatched = [r for r in processed_reports if r.status == "skipped_unmatched"]
        skipped_external = [r for r in processed_reports if r.status == "skipped_external_change"]
        skipped_overlap = [r for r in processed_reports if r.status == "skipped_overlap"]
        failed_apply = [r for r in processed_reports if not r.is_successful() and r.status not in {"skipped_unmatched", "skipped_external_change", "skipped_overlap", "no_action"}]
        discrepancies = [r for r in processed_reports if r.is_successful() and "discrepancies" in r.message]

        def get_rel_path(p: Path) -> str:
            if project_root:
                try: return str(p.relative_to(project_root))
                except ValueError: return p.name
            return p.name

        if skipped_unmatched: summary_lines.append(f"\nSkipped due to unmatched hunks:\n- " + "\n- ".join([get_rel_path(p.file_path) for p in skipped_unmatched]))
        if skipped_external: summary_lines.append(f"\nSkipped due to external changes:\n- " + "\n- ".join([get_rel_path(p.file_path) for p in skipped_external]))
        if skipped_overlap: summary_lines.append(f"\nSkipped due to overlapping hunks:\n- " + "\n- ".join([get_rel_path(p.file_path) for p in skipped_overlap]))
        if discrepancies: summary_lines.append(f"\nApplied with discrepancies (Review Recommended):\n- " + "\n- ".join([get_rel_path(p.file_path) for p in discrepancies]))
        if failed_apply or failed_legacy_files:
             failed_list = [f"{get_rel_path(r.file_path)} ({r.message})" for r in failed_apply] + failed_legacy_files
             summary_lines.append(f"\nFailed files:\n- " + "\n- ".join(failed_list))

        summary = "\n".join(summary_lines)
        if skipped_unmatched or skipped_external or skipped_overlap or failed_apply or failed_legacy_files or discrepancies:
            QMessageBox.warning(self.widget, "Apply All Finished (with issues)", summary)
        else:
            QMessageBox.information(self.widget, "Apply All Finished", summary)

    def reject_all(self):
        """Rejects all pending, matched, or unmatched suggestions/hunks."""
        items_to_reject = []
        paths_to_remove = []
        for path, suggestion_list in self.widget._suggestions.items():
            reject_path = False
            for suggestion in suggestion_list:
                if suggestion.status in {'pending', 'matched', 'unmatched'}:
                    items_to_reject.append(suggestion)
                    reject_path = True
            if reject_path:
                paths_to_remove.append(path)
        if not items_to_reject:
            QMessageBox.information(self.widget, "Reject All", "No pending changes found to reject.")
            return
        logger.info(f"Rejecting all {len(items_to_reject)} pending/matched/unmatched suggestions across {len(paths_to_remove)} files.")
        self.widget._suggestions = {
            p: s_list for p, s_list in self.widget._suggestions.items() if p not in paths_to_remove
        }
        rejected_count = len(items_to_reject)
        self.widget.list_manager.update_list()
        self.widget._clear_diff_view()
        QMessageBox.information(self.widget, "Reject All Finished", f"Rejected {rejected_count} suggestions.")

    def _process_apply_report(self, report: ApplyReport, suggestions_for_path: List[DiffBase]):
        """Processes a single ApplyReport, updates UI and shows messages."""
        file_rel_path = report.file_path.name
        if self.widget._project_root:
            try:
                file_rel_path = report.file_path.relative_to(self.widget._project_root)
            except ValueError:
                pass

        if report.is_successful():
            logger.info(f"Successfully applied suggestion(s) for: {file_rel_path}. {report.message or ''}")
            if report.file_path in self.widget._suggestions:
                # Mark all suggestions for this path as accepted before removing
                for s in self.widget._suggestions[report.file_path]:
                    s.status = 'accepted'
                del self.widget._suggestions[report.file_path]
            # Show message only if processing a single file's worth of changes
            if self.widget._current_suggestion and self.widget._current_suggestion.path == report.file_path:
                 if "discrepancies" in report.message:
                      QMessageBox.warning(self.widget, "Applied with Discrepancies", f"Changes applied to:\n{file_rel_path}\n\nWarning: {report.message}")
                 else:
                      QMessageBox.information(self.widget, "Success", f"Changes applied successfully to:\n{file_rel_path}\n\n{report.message or ''}")

        elif report.status == "skipped_external_change":
             logger.warning(f"Apply skipped for {file_rel_path} due to external changes: {report.message}")
             QMessageBox.warning(self.widget, "Apply Skipped", f"Changes NOT applied to:\n{file_rel_path}\n\nReason: {report.message}")
             # Keep status as 'matched' or 'pending'

        elif report.status == "skipped_unmatched":
             logger.warning(f"Apply skipped for {file_rel_path} due to unmatched hunks.")
             QMessageBox.warning(self.widget, "Apply Skipped", f"Changes NOT applied to:\n{file_rel_path}\n\nReason: One or more changes could not be located.")
             # Status already set to 'unmatched'

        elif report.status == "skipped_overlap":
             logger.error(f"Apply skipped for {file_rel_path} due to overlapping hunks: {report.message}")
             QMessageBox.critical(self.widget, "Apply Error", f"Changes NOT applied to:\n{file_rel_path}\n\nReason: {report.message}")
             # Keep status as 'matched'

        else: # Handle other failures
            logger.error(f"Failed to apply suggestion(s) for {file_rel_path}: {report.status} - {report.message}")
            QMessageBox.critical(self.widget, "Apply Error", f"Failed to apply changes to:\n{file_rel_path}\n\nStatus: {report.status}\nError: {report.message}")
            # Keep status as 'matched' or 'pending'

        # Update list regardless of outcome
        self.widget.list_manager.update_list()