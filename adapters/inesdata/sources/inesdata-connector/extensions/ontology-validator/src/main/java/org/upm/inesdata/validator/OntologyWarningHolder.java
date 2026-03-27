package org.upm.inesdata.validator;

public class OntologyWarningHolder {
    private static final ThreadLocal<String> warning = new ThreadLocal<>();

    public static void set(String msg) { warning.set(msg); }
    public static String get() { return warning.get(); }
    public static void clear() { warning.remove(); }
}