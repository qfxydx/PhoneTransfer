package com.phonetransfer.clip;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Looper;
import android.os.Process;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;

/**
 * PhoneTransfer Android 剪贴板反射桥接工具
 *
 * 通过 app_process 运行在 Android shell (UID 2000) 环境下，
 * 借由反射机制获取 com.android.shell 应用上下文以突破 Android 10+ 后台剪贴板安全沙箱。
 *
 * 功能：
 * 1. 无参数：读取当前系统剪贴板内容并输出至 stdout
 * 2. 参数为 "-"：从 stdin 以 UTF-8 读取任意长度文本、中英文、多行和 Emoji 并写入系统剪贴板
 * 3. 普通参数：拼接参数写入系统剪贴板
 */
public class ClipTool {
    public static void main(String[] args) {
        try {
            Looper.prepareMainLooper();
            Class<?> activityThreadClass = Class.forName("android.app.ActivityThread");
            Object actThread = activityThreadClass.getMethod("systemMain").invoke(null);
            Context systemContext = (Context) activityThreadClass.getMethod("getSystemContext").invoke(actThread);

            Context appContext;
            if (Process.myUid() == 2000) {
                // 在 shell UID (2000) 下构造 shell 上下文，保证 OpPackageName 为 "com.android.shell"
                try {
                    Class<?> compatInfoClass = Class.forName("android.content.res.CompatibilityInfo");
                    Object compatInfo = systemContext.getResources().getClass().getMethod("getCompatibilityInfo").invoke(systemContext.getResources());
                    Method getPackageInfo = activityThreadClass.getMethod("getPackageInfo", String.class, compatInfoClass, int.class, int.class);
                    Object loadedApk = getPackageInfo.invoke(actThread, "com.android.shell", compatInfo, 1073741824 /* Context.CONTEXT_REGISTER_PACKAGE */, 0);
                    Method makeApplication = loadedApk.getClass().getMethod("makeApplication", boolean.class, Class.forName("android.app.Instrumentation"));
                    appContext = (Context) makeApplication.invoke(loadedApk, false, null);
                } catch (Throwable t) {
                    // 若个别魔改 ROM 不支持 makeApplication，平滑回退到 systemContext
                    appContext = systemContext;
                }
            } else {
                appContext = systemContext;
            }

            ClipboardManager cm = (ClipboardManager) appContext.getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm == null) {
                System.err.println("ERR: ClipboardManager unavailable");
                System.exit(2);
            }

            if (args.length == 0) {
                // 读取手机剪贴板
                ClipData data = cm.getPrimaryClip();
                if (data != null && data.getItemCount() > 0) {
                    CharSequence text = data.getItemAt(0).getText();
                    if (text != null) {
                        System.out.print(text.toString());
                    }
                }
            } else if (args.length == 1 && "-".equals(args[0])) {
                // 从 stdin (UTF-8) 读取长文本写入剪贴板，彻底避免 shell 参数长度限制与特殊字符转义问题
                BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
                StringBuilder sb = new StringBuilder();
                char[] buf = new char[4096];
                int n;
                while ((n = reader.read(buf)) != -1) {
                    sb.append(buf, 0, n);
                }
                ClipData data = ClipData.newPlainText("", sb.toString());
                cm.setPrimaryClip(data);
            } else {
                // 普通参数写入
                String text = String.join(" ", args);
                ClipData data = ClipData.newPlainText("", text);
                cm.setPrimaryClip(data);
            }
        } catch (Throwable t) {
            t.printStackTrace();
            System.exit(1);
        }
        System.exit(0);
    }
}
