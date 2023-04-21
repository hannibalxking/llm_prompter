# promptbuilder/cli/filters.py

import fnmatch
from pathlib import Path
from typing import Optional, List, Set

from loguru import logger

from ..core.models import FileNode


def _filter_nodes(
    nodes: List[FileNode],
    root_path: Path,
    include_patterns: Optional[List[str]],
    exclude_patterns: Optional[List[str]]
) -> List[FileNode]:
    """
    Filters a list of FileNode objects based on include/exclude glob patterns
    applied to paths relative to the root_path.

    Keeps parent directories if any of their children are kept.

    Args:
        nodes: The initial list of FileNode objects (typically top-level items).
        root_path: The absolute root path used for relative calculations.
        include_patterns: List of glob patterns to include. If None or empty, all nodes are initially considered.
        exclude_patterns: List of glob patterns to exclude after includes.

    Returns:
        A flat list containing *only* the FileNode objects (both files and directories)
        that were ultimately kept after applying include and exclude rules.
        The hierarchical structure is *not* rebuilt in the returned list.
    """
    if not include_patterns and not exclude_patterns:
        return nodes # No filtering needed

    kept_paths: Set[Path] = set() # Store paths of nodes that should be kept

    # --- Inclusion Pass ---
    nodes_to_consider = nodes
    if include_patterns:
        logger.debug(f"Applying include patterns: {include_patterns}")
        included_paths_pass1: Set[Path] = set()
        # Use a stack for iterative traversal of the initial node list and their children
        stack: List[FileNode] = list(nodes_to_consider)
        processed_for_include: Set[Path] = set() # Avoid reprocessing nodes

        while stack:
            node = stack.pop()
            if node.path in processed_for_include: continue
            processed_for_include.add(node.path)

            try:
                relative_path = node.path.relative_to(root_path).as_posix()
            except ValueError:
                relative_path = node.name # Fallback

            is_match = False
            for pattern in include_patterns:
                if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(node.name, pattern):
                    is_match = True
                    break

            if is_match:
                # If a node matches, keep it and ensure all its parents are also marked
                curr = node
                while curr is not None:
                    if curr.path in included_paths_pass1: break # Already marked up this branch
                    included_paths_pass1.add(curr.path)
                    curr = curr.parent
            # Always traverse children, regardless of parent match status,
            # as a child might match an include pattern even if the parent doesn't.
            if node.is_dir:
                stack.extend(node.children) # Add children to the stack

        kept_paths = included_paths_pass1
        logger.info(f"Include pass identified {len(kept_paths)} potential paths.")
    else:
        # No include patterns: initially consider all paths from the input nodes and their descendants
        stack = list(nodes)
        all_paths: Set[Path] = set()
        processed_all: Set[Path] = set()
        while stack:
             node = stack.pop()
             if node.path in processed_all: continue
             processed_all.add(node.path)
             all_paths.add(node.path)
             if node.is_dir: stack.extend(node.children)
        kept_paths = all_paths
        logger.info("No include patterns, considering all scanned paths initially.")


    # --- Exclusion Pass ---
    if exclude_patterns:
        logger.debug(f"Applying exclude patterns: {exclude_patterns}")
        paths_to_exclude: Set[Path] = set()
        # Check all potentially kept paths against exclusion rules
        # Iterate through all original nodes again to check patterns
        stack = list(nodes)
        processed_for_exclude: Set[Path] = set()

        while stack:
             node = stack.pop()
             if node.path in processed_for_exclude: continue
             processed_for_exclude.add(node.path)

             # Only check nodes that were potentially kept by the include pass
             if node.path not in kept_paths:
                  if node.is_dir: stack.extend(node.children) # Still need to check children
                  continue

             try:
                relative_path = node.path.relative_to(root_path).as_posix()
             except ValueError:
                relative_path = node.name

             is_excluded = False
             for pattern in exclude_patterns:
                 if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(node.name, pattern):
                     is_excluded = True
                     break

             if is_excluded:
                 # If a node is excluded, mark it and all its descendants for removal
                 exclusion_stack = [node]
                 processed_exclusion_stack: Set[Path] = set()
                 while exclusion_stack:
                      ex_node = exclusion_stack.pop()
                      if ex_node.path in processed_exclusion_stack: continue
                      processed_exclusion_stack.add(ex_node.path)

                      paths_to_exclude.add(ex_node.path)
                      if ex_node.is_dir: exclusion_stack.extend(ex_node.children)
             elif node.is_dir: # If directory not excluded, check its children
                  stack.extend(node.children)

        # Remove excluded paths
        final_kept_paths = kept_paths - paths_to_exclude
        logger.info(f"Exclude pass removed {len(paths_to_exclude)} paths. Keeping {len(final_kept_paths)}.")
        kept_paths = final_kept_paths


    # --- Collect the actual FileNode objects corresponding to kept paths ---
    # Fixes regression #2: Clarify that this returns a flat list.
    # The reconstruction of the tree is complex and not needed by the current caller.
    filtered_nodes_flat: List[FileNode] = []
    stack = list(nodes)
    processed_final: Set[Path] = set()
    while stack:
         node = stack.pop()
         if node.path in processed_final: continue
         processed_final.add(node.path)

         if node.path in kept_paths:
              # Add the node itself to the flat list if its path was kept
              filtered_nodes_flat.append(node)

         # Always traverse children, as a child might be kept even if parent wasn't initially added
         # (e.g., parent excluded, but child included by a more specific rule - though current logic might not handle this perfectly)
         if node.is_dir: stack.extend(node.children)

    logger.debug(f"Filter function returning flat list of {len(filtered_nodes_flat)} kept nodes.")
    return filtered_nodes_flat


def _collect_paths_from_nodes(nodes: List[FileNode]) -> Set[Path]:
    """
    Helper to recursively extract all *file* paths from a flat list of FileNode objects.
    It traverses directories found in the list to find nested files.
    """
    paths: Set[Path] = set()
    # Use a stack and track visited directories to handle potential duplicates if
    # the input list contains both a directory and its children.
    stack = list(nodes)
    visited_nodes : Set[Path] = set()

    while stack:
        node = stack.pop()
        if node.path in visited_nodes: continue
        visited_nodes.add(node.path)

        if not node.is_dir:
            paths.add(node.path)
        else:
             # If it's a directory, add its direct children to the stack to process them.
             # This ensures we find files within directories present in the input list.
             stack.extend(node.children)
    return paths