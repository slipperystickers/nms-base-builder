from pathlib import Path
import sys,json,os,tempfile
source=Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder'
site=sys.argv[1]; pid=int(sys.argv[2]); geometry=json.loads(sys.argv[3])
sys.path.insert(0,str(source));sys.argv=[str(source/'bbe_chat_messenger.py'),site,'identity','settings','snapshot']
import bbe_chat_messenger as m
app=m.QtWidgets.QApplication([])
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'identity.json').write_text(json.dumps({'secret':'test-only-no-network','names':[],'active':False}));(p/'settings.json').write_text(json.dumps({'enabled':False,'blender_pid':pid,'chat_viewport':geometry['viewport'],'chat_toolbar':geometry['toolbar']}))
 w=m.Messenger(p/'identity.json',p/'settings.json',p);w.timer.stop();w.snapshot_timer.stop();w.compact_timer.stop();w.show()
 w.mini_action.setChecked(True);w._collapse(False);w.resize(340,300);app.processEvents()
 assert w._native_pin(force=True)
 for side in ('top-right','bottom-right'):
  w._dock(side);app.processEvents();bounds=w._viewport_bounds().adjusted(6,6,-6,-6)
  assert abs(w.geometry().right()-bounds.right())<=2,(side,w.geometry(),bounds)
  assert abs((w.geometry().top()-bounds.top()) if side=='top-right' else (w.geometry().bottom()-bounds.bottom()))<=2
  w._collapse(True);app.processEvents();assert w.height()<=40
  assert abs(w.geometry().right()-bounds.right())<=2
  w._collapse(False);app.processEvents()
 w._dock('toolbar');app.processEvents();row=w._toolbar_bounds()
 assert w.collapsed and abs(w.height()-(row.height()-2))<=2,(w.geometry(),row)
 assert abs(w.y()-row.y()-1)<=1
 assert not w.mask().contains(m.QtCore.QPoint(0,0))
 assert w.grab().toImage().pixelColor(0,0).alpha()==0
 w.grab().save(str(source.parents[2]/'tests/.artifacts/chat-native-strip.png'))
 w._collapse(False)
 w.emoji_menu.popup(w.emoji_button.mapToGlobal(m.QtCore.QPoint(0,0)));app.processEvents()
 assert len(w.emoji_menu.findChildren(m.QtWidgets.QPushButton))==24
 w.emoji_menu.grab().save(str(source.parents[2]/'tests/.artifacts/chat-emoji-menu.png'))
 w.close();app.processEvents()
print('BBE_NATIVE_DOCK_PIN_PASS',flush=True)
