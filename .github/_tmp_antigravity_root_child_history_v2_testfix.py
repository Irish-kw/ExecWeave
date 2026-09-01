from pathlib import Path

path = Path("tests/test_antigravity_root_child_history_v2.py")
text = path.read_text(encoding="utf-8")
old = '''            details = page.locator("#details")
            text = details.inner_text()
            assert "child A first task" in text
            assert "child A first response" in text
            assert "child A second task" in text
            assert "child A second response" in text
            assert "sibling note, not a task" not in text
            assert details.locator(".execweave-agent-older").count() == 1
            older = details.locator(".execweave-agent-older").first
            assert not older.evaluate("node=>node.open")
            older.locator("summary").click()
            assert older.evaluate("node=>node.open")
            page.evaluate("items=>window.__execweaveAgentPanel.setEntries(items)", entries)
            assert details.locator(".execweave-agent-older").first.evaluate("node=>node.open")
'''
new = '''            details = page.locator("#details")
            current = details.inner_text()
            assert "child A second task" in current
            assert "child A second response" in current
            assert "sibling note, not a task" not in current
            assert details.locator(".execweave-agent-older").count() == 1
            older = details.locator(".execweave-agent-older").first
            assert not older.evaluate("node=>node.open")
            older.locator("summary").click()
            assert older.evaluate("node=>node.open")
            expanded = older.inner_text()
            assert "child A first task" in expanded
            assert "child A first response" in expanded
            assert "child A second task" not in expanded
            assert "child A second response" not in expanded
            page.evaluate("items=>window.__execweaveAgentPanel.setEntries(items)", entries)
            persisted = details.locator(".execweave-agent-older").first
            assert persisted.evaluate("node=>node.open")
            persisted_text = persisted.inner_text()
            assert "child A first task" in persisted_text
            assert "child A first response" in persisted_text
'''
if text.count(old) != 1:
    raise SystemExit(f"browser assertion guard failed: {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
