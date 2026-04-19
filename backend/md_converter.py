import markdown2
def convert(md_text: str) -> str:
    """ convert markdown text to html with useful extras"""
    return markdown2.markdown(
        md_text, 
        extras=[
            "fenced-code-blocks", 
            "tables", 
            "strike", 
            "task_list",
            "code-friendly", 
            "header-ids"
        ]
    )