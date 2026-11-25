import java.awt.AWTException;
import java.awt.Color;
import java.awt.Component;
import java.awt.Container;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Point;
import java.awt.Rectangle;
import java.awt.Robot;
import java.awt.Toolkit;
import java.awt.Window;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;
import java.io.File;
import java.io.OutputStream;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

import javax.imageio.ImageIO;
import javax.swing.AbstractButton;
import javax.swing.BorderFactory;
import javax.swing.JLabel;
import javax.swing.JTable;
import javax.swing.JWindow;
import javax.swing.SwingConstants;
import javax.swing.SwingUtilities;
import javax.swing.text.JTextComponent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Records one tutorial of the desktop client: starts Open Hospital in this JVM, plays the steps of a scenario with the
 * real mouse and keyboard (java.awt.Robot), shows the captions in a small window, records the screen with ffmpeg and
 * writes the captions as WebVTT plus one screenshot per step.
 *
 * Selectors: "window:SimpleClassName", "button:Text", "field:N@Window" (N-th text field of that window),
 * "row:Text@Window" (first table row that contains Text).
 *
 * args: scenario.json, output directory, [dump] to print the components of every window instead of recording.
 */
public class TutorialDesktop {

	static Robot robot;
	static JWindow captionWindow;
	static JLabel captionLabel;
	static boolean dump;

	static <T> T edt(Callable<T> c) throws Exception {
		FutureTask<T> f = new FutureTask<>(c);
		SwingUtilities.invokeLater(f);
		return f.get(60, TimeUnit.SECONDS);
	}

	static Window window(String simpleName) {
		for (Window w : Window.getWindows()) {
			if (w.isShowing() && w != captionWindow && w.getClass().getSimpleName().equals(simpleName)) {
				return w;
			}
		}
		return null;
	}

	static <C> List<C> all(Component root, Class<C> type, List<C> found) {
		if (type.isInstance(root) && root.isShowing()) {
			found.add(type.cast(root));
		}
		if (root instanceof Container c) {
			for (Component child : c.getComponents()) {
				all(child, type, found);
			}
		}
		return found;
	}

	static String clean(String s) {
		return s == null ? "" : s.replaceAll("<[^>]*>", "").trim();
	}

	/** Finds what a selector points at and returns its rectangle on screen, or null while it is not there. */
	static Rectangle find(String selector) throws Exception {
		return edt(() -> {
			String kind = selector.substring(0, selector.indexOf(':'));
			String rest = selector.substring(selector.indexOf(':') + 1);
			String where = rest.contains("@") ? rest.substring(rest.lastIndexOf('@') + 1) : null;
			String what = rest.contains("@") ? rest.substring(0, rest.lastIndexOf('@')) : rest;
			List<Window> windows = new ArrayList<>();
			for (Window w : Window.getWindows()) {
				if (w.isShowing() && w != captionWindow && (where == null || w.getClass().getSimpleName().equals(where))) {
					windows.add(w);
				}
			}
			for (Window w : windows) {
				if (kind.equals("window") && w.getClass().getSimpleName().equals(what)) {
					return w.getBounds();
				}
				if (kind.equals("button")) {
					for (AbstractButton b : all(w, AbstractButton.class, new ArrayList<>())) {
						if (what.equals(clean(b.getText())) && b.isEnabled()) {
							return onScreen(b, null);
						}
					}
				}
				if (kind.equals("field")) {
					List<JTextComponent> fields = all(w, JTextComponent.class, new ArrayList<>());
					fields.removeIf(f -> !f.isEditable());
					int n = Integer.parseInt(what);
					if (n < fields.size()) {
						return onScreen(fields.get(n), null);
					}
				}
				if (kind.equals("row")) {
					for (JTable t : all(w, JTable.class, new ArrayList<>())) {
						for (int r = 0; r < t.getRowCount(); r++) {
							for (int c = 0; c < t.getColumnCount(); c++) {
								if (String.valueOf(t.getValueAt(r, c)).contains(what)) {
									t.scrollRectToVisible(t.getCellRect(r, 0, true));
									Rectangle cell = t.getCellRect(r, c, true);
									return onScreen(t, cell);
								}
							}
						}
					}
				}
			}
			return null;
		});
	}

	static Rectangle onScreen(Component c, Rectangle inside) {
		Point p = c.getLocationOnScreen();
		Rectangle r = inside != null ? new Rectangle(inside) : new Rectangle(0, 0, c.getWidth(), c.getHeight());
		r.translate(p.x, p.y);
		return r;
	}

	static Rectangle waitFor(String selector, int seconds) throws Exception {
		long end = System.currentTimeMillis() + seconds * 1000L;
		while (System.currentTimeMillis() < end) {
			Rectangle r = find(selector);
			if (r != null) {
				return r;
			}
			Thread.sleep(300);
		}
		System.out.println("timeout waiting for " + selector);
		dumpAll();
		throw new IllegalStateException("not found: " + selector);
	}

	static void dumpAll() throws Exception {
		edt(() -> {
			for (Window w : Window.getWindows()) {
				if (w.isShowing() && w != captionWindow) {
					System.out.println("== window " + w.getClass().getSimpleName() + " " + w.getBounds());
					dump(w, "  ");
				}
			}
			return null;
		});
	}

	static void dump(Component c, String indent) {
		if (!c.isShowing()) {
			return;
		}
		String text = c instanceof AbstractButton b ? clean(b.getText()) : c instanceof JLabel l ? clean(l.getText())
						: c instanceof JTextComponent t ? "[" + t.getText() + "] editable=" + t.isEditable() : "";
		if (!text.isEmpty() || c instanceof JTable) {
			System.out.println(indent + c.getClass().getSimpleName() + " " + text);
		}
		if (c instanceof Container k) {
			for (Component child : k.getComponents()) {
				dump(child, indent + " ");
			}
		}
	}

	static void move(Rectangle r) throws InterruptedException {
		Point from = java.awt.MouseInfo.getPointerInfo().getLocation();
		int tx = r.x + r.width / 2;
		int ty = r.y + r.height / 2;
		for (int i = 1; i <= 30; i++) {
			robot.mouseMove(from.x + (tx - from.x) * i / 30, from.y + (ty - from.y) * i / 30);
			Thread.sleep(20);
		}
		Thread.sleep(400);
	}

	static void click(Rectangle r) throws InterruptedException {
		move(r);
		robot.mousePress(InputEvent.BUTTON1_DOWN_MASK);
		robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
		Thread.sleep(300);
	}

	static void type(String text) throws InterruptedException {
		for (char ch : text.toCharArray()) {
			int code = KeyEvent.getExtendedKeyCodeForChar(Character.toLowerCase(ch));
			boolean shift = Character.isUpperCase(ch);
			if (shift) {
				robot.keyPress(KeyEvent.VK_SHIFT);
			}
			robot.keyPress(code);
			robot.keyRelease(code);
			if (shift) {
				robot.keyRelease(KeyEvent.VK_SHIFT);
			}
			Thread.sleep(120);
		}
	}

	static void caption(String text) throws Exception {
		edt(() -> {
			captionLabel.setText("<html><div style='text-align:center'>" + text + "</div></html>");
			Dimension screen = Toolkit.getDefaultToolkit().getScreenSize();
			captionWindow.setSize(900, 70);
			captionWindow.setLocation((screen.width - 900) / 2, screen.height - 110);
			captionWindow.setVisible(true);
			captionWindow.toFront();
			return null;
		});
	}

	static String vttTime(double s) {
		long ms = Math.round(s * 1000);
		return String.format("%02d:%02d:%02d.%03d", ms / 3600000, ms / 60000 % 60, ms / 1000 % 60, ms % 1000);
	}

	public static void main(String[] args) throws Exception {
		JsonNode sc = new ObjectMapper().readTree(new File(args[0]));
		File out = new File(args[1]);
		out.mkdirs();
		dump = args.length > 2 && args[2].equals("dump");
		robot = new Robot();
		edt(() -> {
			captionWindow = new JWindow();
			captionWindow.setFocusableWindowState(false);
			captionWindow.setAlwaysOnTop(true);
			captionLabel = new JLabel("", SwingConstants.CENTER);
			captionLabel.setOpaque(true);
			captionLabel.setBackground(new Color(30, 30, 30));
			captionLabel.setForeground(Color.WHITE);
			captionLabel.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 20));
			captionLabel.setBorder(BorderFactory.createEmptyBorder(8, 16, 8, 16));
			captionWindow.add(captionLabel);
			return null;
		});
		// a new installation asks about telemetry in a modal dialog: close it whenever it shows up
		Thread telemetry = new Thread(() -> {
			while (true) {
				SwingUtilities.invokeLater(() -> {
					Window w = window("TelemetryEdit");
					if (w != null) {
						w.dispose();
					}
				});
				try {
					Thread.sleep(500);
				} catch (InterruptedException e) {
					return;
				}
			}
		});
		telemetry.setDaemon(true);
		telemetry.start();

		Dimension screen = Toolkit.getDefaultToolkit().getScreenSize();
		Process ffmpeg = null;
		if (!dump) {
			ffmpeg = new ProcessBuilder("ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "1", "-framerate", "25",
							"-video_size", screen.width + "x" + screen.height, "-i", System.getenv().getOrDefault("DISPLAY", ":0"),
							"-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", new File(out, "raw.mp4").getPath())
							.redirectErrorStream(true).redirectOutput(new File(out, "ffmpeg.log")).start();
		}
		long t0 = System.currentTimeMillis();
		robot.mouseMove(screen.width / 2, screen.height / 2);
		org.isf.Application.main();

		StringBuilder vtt = new StringBuilder("WEBVTT\n\n");
		int i = 0;
		for (JsonNode s : sc.get("steps")) {
			i++;
			if (s.has("wait") && !s.has("click")) {
				waitFor(s.get("wait").asText(), 240);
			}
			if (dump) {
				System.out.println("##### step " + i + ": " + s.get("caption").asText());
				dumpAll();
			}
			double start = (System.currentTimeMillis() - t0) / 1000.0;
			caption(s.get("caption").asText());
			Thread.sleep(1500);
			if (s.has("type")) {
				for (Iterator<Map.Entry<String, JsonNode>> it = s.get("type").fields(); it.hasNext();) {
					Map.Entry<String, JsonNode> e = it.next();
					click(waitFor(e.getKey(), 30));
					type(e.getValue().asText());
					Thread.sleep(300);
				}
			}
			if (s.has("point")) {
				move(waitFor(s.get("point").asText(), 30));
			}
			ImageIO.write(robot.createScreenCapture(new Rectangle(screen)), "png", new File(out, String.format("step%02d.png", i)));
			if (s.has("click")) {
				click(waitFor(s.get("click").asText(), 30));
				if (s.has("wait")) {
					waitFor(s.get("wait").asText(), 60);
				}
			}
			Thread.sleep(s.has("hold") ? s.get("hold").asInt() : 1500);
			double end = (System.currentTimeMillis() - t0) / 1000.0;
			vtt.append(i).append('\n').append(vttTime(start)).append(" --> ").append(vttTime(end)).append('\n')
							.append(s.get("caption").asText()).append("\n\n");
		}
		Files.writeString(new File(out, sc.get("id").asText() + ".en.vtt").toPath(), vtt.toString());
		if (ffmpeg != null) {
			OutputStream in = ffmpeg.getOutputStream();
			in.write('q');
			in.flush();
			ffmpeg.waitFor(30, TimeUnit.SECONDS);
		}
		System.out.println("done " + i + " steps, " + (System.currentTimeMillis() - t0) / 1000 + " s");
		System.exit(0);
	}
}
