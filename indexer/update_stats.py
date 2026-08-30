from pathlib import Path

# coverage stats
p = Path(__file__).resolve().parent.parent / "app" / "coverage.html"
t = p.read_text()
t = t.replace('<div class="text-2xl font-bold text-green-700">15</div>',
              '<div class="text-2xl font-bold text-green-700">18</div>')
t = t.replace('<div class="text-2xl font-bold text-slate-600">8+</div>',
              '<div class="text-2xl font-bold text-slate-600">4+</div>')
p.write_text(t)
print("coverage stats: 18 covered / 4+ deferred")

# landing chunks stat
p2 = Path(__file__).resolve().parent.parent / "app" / "index.html"
t2 = p2.read_text()
t2 = t2.replace('<div id="stat-chunks" class="text-3xl font-bold">4,186</div>',
                '<div id="stat-chunks" class="text-3xl font-bold">4,872</div>')
p2.write_text(t2)
print("landing stats: 4,872 chunks")
