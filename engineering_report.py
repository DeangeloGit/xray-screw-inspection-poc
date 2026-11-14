"""Render a standalone engineering HTML report."""
from base64 import b64encode


def write_report(app, directory, run, result, candidates, record, steps):
    names = {name for _, _, images in steps for name in images if (directory / name).is_file()}
    names.update(name for candidate in candidates for name in candidate['debug_images'])
    images = {name: 'data:image/png;base64,' + b64encode((directory / name).read_bytes()).decode('ascii')
              for name in names}
    with app.app_context():
        report = app.jinja_env.get_template('engineering_trace_report.html').render(
            run=run, result=result, candidates=candidates, record=record, steps=steps, images=images)
    (directory / 'report.html').write_text(report, encoding='utf-8')
