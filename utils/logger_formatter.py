"""
Logger Formatter Utilities
Provides box drawing and formatting functions for terminal output
"""

def box_header(content, width=60):
    """Create a box header for major events"""
    lines = content.split('\n')
    top = "╔" + "═" * (width - 2) + "╗"
    bottom = "╚" + "═" * (width - 2) + "╝"
    
    formatted_lines = [top]
    for line in lines:
        # Pad line to width
        padded = f"{line:\u003c{width - 4}}"
        formatted_lines.append(f"║  {padded}║")
    formatted_lines.append(bottom)
    
    return "\n" + "\n".join(formatted_lines)


def section_header(title, width=64):
    """Create a section header for subsections"""
    top = "┌" + "─" * (width - 2) + "┐"
    middle = f"│ {title:<{width - 3}}│"
    bottom = "└" + "─" * (width - 2) + "┘"
    return f"\n{top}\n{middle}\n{bottom}\n"


def separator(width=64):
    """Create a separator line"""
    return "═" * width


def format_call_header(call_number, customer_name, phone, route=None, agency=None, time_str=None):
    """Format a call initiation header"""
    lines = [
        f"║  📞 CALL #{call_number} INITIATED                                          ║",
        f"║  Customer: {customer_name} ({phone})                                 ║",
    ]
    
    if route:
        lines.append(f"║  Route: {route:<50}║")
    
    if agency:
        lines.append(f"║  Agency: {agency:<49}║")
    
    if time_str:
        lines.append(f"║  Time: {time_str:<52}║")
    
    top = "╔" + "═" * 62 + "╗"
    bottom = "╚" + "═" * 62 + "╝"
    
    return f"\n{top}\n" + "\n".join(lines) + f"\n{bottom}\n"


def format_error_box(title, details_dict, width=64):
    """Format an error box with details"""
    top = "╔" + "═" * (width - 2) + "╗"
    title_line = f"║  {title:<{width - 4}}║"
    divider = "╠" + "═" * (width - 2) + "╣"
    bottom = "╚" + "═" * (width - 2) + "╝"
    
    lines = [top, title_line, divider]
    
    for key, value in details_dict.items():
        line = f"║  {key}: {value:<{width - len(key) - 6}}║"
        lines.append(line)
    
    lines.append(bottom)
    
    return "\n" + "\n".join(lines) + "\n"


def format_summary_box(title, items, width=64):
    """Format a summary box with items"""
    top = "╔" + "═" * (width - 2) + "╗"
    title_line = f"║  {title:<{width - 4}}║"
    empty_line = "║" + " " * (width - 2) + "║"
    bottom = "╚" + "═" * (width - 2) + "╝"
    
    lines = [top, title_line, empty_line]
    
    for item in items:
        line = f"║  {item:<{width - 4}}║"
        lines.append(line)
    
    lines.append(empty_line)
    lines.append(bottom)
    
    return "\n" + "\n".join(lines) + "\n"
