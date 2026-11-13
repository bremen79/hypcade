/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
public final class ArcadeSetupTest {
    private static void check(boolean value,String message) {if(!value) throw new AssertionError(message);}
    public static void main(String[] args) throws Exception {
        ControlMap emptyControls = new ControlMap();
        check(emptyControls.canPlay(false, true), "Mobile touch needs no controller");
        check(!emptyControls.canPlay(false, false), "Mobile requires some input");
        check(!emptyControls.canPlay(true, true), "Arcade requires controller even if touch requested");
        check(!emptyControls.canPlay(true, false), "Arcade blocks missing controller");
        for (String game : new String[]{"ace", "dle21", "lair2"}) {
            GuidanceSupport support = GuidanceSupport.forArguments(new String[]{game, "vldp"});
            check(support.visual && support.cue == !game.equals("lair2"), "Supported ROM guidance");
            check(!GuidanceSupport.forArguments(new String[]{game,"-VERSION","2"}).visual, "Unsupported revision");
            check(!GuidanceSupport.forArguments(new String[]{game,"-version"}).visual, "Missing revision");
        }
        check(!GuidanceSupport.forArguments(new String[]{"ace","-version","1","-version","2"}).cue, "Repeated revision cannot bypass guard");
        check(!GuidanceSupport.forArguments(new String[]{"lair"}).visual, "No table for original lair");
        GuidanceSupport singeSupport = GuidanceSupport.forArguments(new String[]{"singe","-script","SAe.singe"});
        check(singeSupport.scriptControlled && !singeSupport.visual && !singeSupport.cue, "Lua owns moves and cues");
        check(!GuidanceSupport.forArguments(null).visual, "Smoke test has no guidance");
        check(ControlMap.KEYS[11] == 16 && ControlMap.optional(11), "Game options maps to native service key 9");
        Path root=Files.createDirectories(Path.of(args[0],"scan-games"));
        for(String game:new String[]{"ace","dle21","lair2"}) {
            Path dir=Files.createDirectories(root.resolve(game+".daphne"));
            Files.writeString(dir.resolve(game+".txt"),".\n0 video.m2v\n");
            Files.write(dir.resolve("video.m2v"),new byte[]{0,0,1});
            Files.writeString(dir.resolve("readme.txt"),"not a framefile");
        }
        Path outside=Files.createDirectories(root.getParent().resolve("outside-scan"));
        Files.writeString(outside.resolve("ace.txt"),".\n0 video.m2v\n");
        Files.createSymbolicLink(root.resolve("escape"),outside);
        Files.createSymbolicLink(root.resolve("loop"),root);
        GameScanner.Result found=GameScanner.scan(root.toFile(),Collections.emptyList(),()->false);
        check(found.games.size()==3,"Discover three valid games, ignore bad framefiles and escaped/cyclic links");
        for (LaunchConfig detected : found.games) {
            check(detected.showScore, "Default score preference enabled");
            check(new VideoOptions(LaunchConfig.splitArguments(detected.extraArguments)).smooth,
                    "New game profiles default to smooth video scaling");
            check(LaunchConfig.splitArguments(detected.extraArguments).contains("-fastboot") ==
                    LaunchConfig.supportsFastBoot(detected.game), "Fast boot defaults on where supported");
        }
        Path commands = root.resolve("ace.daphne/ace.commands");
        Files.writeString(commands, "\ufeff# test\r\n-SCANLINES -novsync -software_video -showfps "
                + "-bank 0 0010 -bank 1 1000 -version 1 -bezel \"name # one.png\" "
                + "-framefile \"/desktop/frame file.txt\" -x 640 -y 480 -rotate -90 "
                + "-config old.ini -nojoystick -useoverlaysb 2 # trailing comment\n");
        LaunchConfig imported = GameScanner.scan(root.toFile(), Collections.emptyList(), ()->false)
                .games.stream().filter(c->c.game.equals("ace")).findFirst().orElseThrow();
        java.util.List<String> importedArgs = LaunchConfig.splitArguments(imported.extraArguments);
        VideoOptions importedVideo = new VideoOptions(importedArgs);
        check(importedVideo.scanlines && !importedVideo.vsync && importedVideo.showFps
                && !importedVideo.fastBoot && !importedVideo.smooth,
                "Command-file settings override new-profile defaults");
        check(importedArgs.contains("name # one.png") && java.util.Collections.frequency(importedArgs,"-bank")==2,
                "Preserve quoted values, comments, repeated ROM banks");
        check(!importedArgs.contains("-framefile") && !importedArgs.contains("-x") && !importedArgs.contains("-config")
                && !importedArgs.contains("-nojoystick") && !importedArgs.contains("2"), "Android owns paths, display, controls and score");
        importedVideo.scanlines=false; importedVideo.vsync=true;
        LaunchConfig edited = new LaunchConfig(imported.id, imported.name, imported.game, imported.framefile,
                imported.script, importedVideo.arguments(importedArgs), MoveMode.OFF, false, false);
        Files.writeString(commands, "-scanlines -novsync -fastboot -bank 0 1111");
        LaunchConfig rescanned = GameScanner.scan(root.toFile(), Collections.singletonList(edited), ()->false)
                .games.stream().filter(c->c.id.equals(edited.id)).findFirst().orElseThrow();
        check(rescanned == edited && !rescanned.showScore && !new VideoOptions(LaunchConfig.splitArguments(rescanned.extraArguments)).scanlines
                && !new VideoOptions(LaunchConfig.splitArguments(rescanned.extraArguments)).smooth,
                "Rescan preserves GUI choices and imported native options despite changed file");
        check(!java.util.Arrays.asList(edited.arguments(root.toFile())).contains("-scorebezel"), "GUI score off wins");
        Files.writeString(commands, "-bezel \"unfinished");
        check(!GameScanner.scan(root.toFile(), Collections.emptyList(), ()->false).commandErrors.isEmpty(), "Malformed commands reported");
        Files.writeString(commands, "-framefile");
        check(!GameScanner.scan(root.toFile(), Collections.emptyList(), ()->false).commandErrors.isEmpty(), "Missing managed value reported");
        Files.writeString(commands, "x".repeat(8193));
        check(!GameScanner.scan(root.toFile(), Collections.emptyList(), ()->false).commandErrors.isEmpty(), "Bound command file size");
        Files.delete(commands);
        Files.writeString(outside.resolve("escape.commands"), "-scanlines");
        Files.createSymbolicLink(commands, outside.resolve("escape.commands"));
        check(!GameScanner.scan(root.toFile(), Collections.emptyList(), ()->false).commandErrors.isEmpty(), "Reject escaped command symlink");
        Files.delete(commands);
        LaunchConfig original=found.games.get(0);
        LaunchConfig saved=new LaunchConfig(original.id,"My custom settings",original.game,original.framefile,"","-fastboot",MoveMode.MAX_SCORE,true);
        GameScanner.Result again=GameScanner.scan(root.toFile(),Collections.singletonList(saved),()->false);
        check(again.games.stream().anyMatch(c->c.id.equals(saved.id) && c.moveMode == MoveMode.MAX_SCORE && c.extraArguments.equals("-fastboot")),"Preserve saved settings");
        check(GameScanner.scan(root.toFile(),Collections.emptyList(),()->true).games.isEmpty(),"Cancellation");
        Files.delete(root.resolve("ace.daphne/video.m2v"));
        check(GameScanner.scan(root.toFile(),Collections.emptyList(),()->false).games.size()==2,"Exclude missing media");
        Path singe=Files.createDirectories(root.resolve("singe/custom"));
        Files.writeString(singe.resolve("custom.txt"),".\n0 video.m2v\n");
        Files.write(singe.resolve("video.m2v"),new byte[]{0,0,1});
        Files.writeString(singe.resolve("custom.singe"),"-- fixture");
        check(GameScanner.scan(root.toFile(),Collections.emptyList(),()->false).games.stream()
            .anyMatch(c->c.game.equals("singe") && c.script.equals("singe/custom/custom.singe")),"Pair Singe script automatically");
        Files.writeString(root.resolve("ace.daphne/custom.lst"),".\n0 video.m2v\n");
        Files.write(root.resolve("ace.daphne/video.m2v"),new byte[]{0,0,1});
        LaunchConfig manual=new LaunchConfig("manual","Manual legacy game","ace","ace.daphne/custom.lst","","");
        check(GameScanner.scan(root.toFile(),Collections.singletonList(manual),()->false).games.stream()
            .anyMatch(c->c.id.equals("manual")),"Preserve explicit nonstandard framefiles");
        java.util.List<String> inherited=LaunchConfig.splitArguments("-SCANLINES -scanlines -BLEND -NOVSYNC -linear_scale -fastboot -bank 0 0010 -bezel \"name with spaces.png\"");
        VideoOptions video=new VideoOptions(inherited);
        check(video.scanlines && video.smooth && !video.vsync && video.fastBoot,"Read legacy options case-insensitively");
        video.scanlines=false;video.smooth=false;video.vsync=true;
        java.util.List<String> output=LaunchConfig.splitArguments(video.arguments(inherited));
        check(output.equals(java.util.Arrays.asList("-BLEND","-bank","0","0010","-bezel","name with spaces.png","-fastboot")),"Disable flags without losing unrelated options");
        video.scanlines=true;video.vsync=false;
        output=LaunchConfig.splitArguments(video.arguments(inherited));
        check(java.util.Collections.frequency(output,"-scanlines")==1 && output.contains("-BLEND") && output.contains("-novsync"),"No duplicate flags");
        check(output.contains("-BLEND"), "Command-file blend is preserved without a GUI control");
        video.fastBoot = false;
        java.util.List<String> slow = LaunchConfig.splitArguments(video.arguments(output));
        check(!slow.contains("-fastboot"), "Fast startup off removes the native fastboot flag");
        check(new VideoOptions(java.util.Collections.emptyList()).vsync,"Keep default V-sync enabled");
        VideoOptions fps=new VideoOptions(java.util.Collections.emptyList());
        check(!fps.showFps,"FPS defaults off");fps.showFps=true;
        java.util.List<String> fpsArgs=LaunchConfig.splitArguments(fps.arguments(java.util.Collections.emptyList()));
        check(new VideoOptions(fpsArgs).showFps,"FPS persists");fps.showFps=false;
        check(!fps.arguments(fpsArgs).contains("-showfps"),"FPS can be disabled");
        String[] old={"dle21","vldp","-framefile","/sd/games.txt","-ROTATE","90","-x","1920","-y","1080","-scanlines"};
        java.util.List<String> fixed=java.util.Arrays.asList(ArcadeDisplay.arguments(old,1280,960));
        check(fixed.contains("/sd/games.txt") && fixed.contains("-scanlines"),"Preserve game and video preferences");
        check(!fixed.contains("90") && !fixed.contains("1920") && !fixed.contains("1080"),"Replace inherited display overrides");
        check(fixed.get(fixed.indexOf("-x")+1).equals("1280") && fixed.get(fixed.indexOf("-y")+1).equals("960"),"Cabinet resolution");
        check(fixed.get(fixed.indexOf("-rotate")+1).equals("0"),"No media rotation");
        check(java.util.Arrays.equals(ArcadeDisplay.arguments(new String[]{"--android-smoke-test"},1280,960),new String[]{"--android-smoke-test"}),"Keep smoke-test entry point");
        java.util.List<String> rotated=java.util.Arrays.asList(ArcadeDisplay.arguments(old,600,800));
        check(rotated.get(rotated.indexOf("-x")+1).equals("800") && rotated.get(rotated.indexOf("-y")+1).equals("600"),"Native landscape size on other cabinets");
        check(!new VideoOptions(java.util.Collections.emptyList()).arguments(java.util.Collections.emptyList()).contains("-software_video"),"Automatic hardware decoding needs no launcher flag");
        ControlMap map=new ControlMap();
        check(map.add(new ControlMap.Binding(0,"USB|日本語",19,2,-1,0)),"First binding");
        check(!map.add(new ControlMap.Binding(1,"USB|日本語",19,2,-1,0)),"Reject duplicate physical button");
        check(map.add(new ControlMap.Binding(1,"USB|日本語",0,0,1,1)),"Axis binding");
        check(map.add(new ControlMap.Binding(2,"USB|日本語",0,0,1,-1)),"Opposite axis direction");
        check(map.encode().contains("0|VVNCfOaXpeacrOiqng==|19|2|-1|0\n"),
                "Keep the persisted Base64 format across Android API levels");
        ControlMap decoded=ControlMap.decode(map.encode());
        check(decoded.encode().equals(map.encode()),"Lossless persisted mapping");
        check(ControlMap.decode(map.encode()+"    ").bindings.size()==3,"Preference XML trailing indentation");
        check(decoded.bindings.get(0).keyMatches(19,2),"Scancode match");
        check(!decoded.bindings.get(0).keyMatches(19,3),"Distinct physical scancode");
        check(ControlMap.decode("1\ninvalid").bindings.isEmpty(),"Corrupt mapping fallback");
        check(ControlMap.decode("2\n").bindings.isEmpty(),"Unknown version fallback");
        check(!new ControlMap().isComplete(), "Empty setup is blocked");
        check(!decoded.isComplete(), "Partial setup is blocked");
        ControlMap required = new ControlMap();
        for (int action=0; action<ControlMap.NAMES.length; action++)
            if (!ControlMap.optional(action)) required.add(new ControlMap.Binding(action,"keyboard",30+action,0,-1,0));
        check(required.isComplete(), "Optional actions may be skipped");
        check(required.canPlay(false, false), "Configured mobile works without touch");
        check(required.canPlay(false, true), "Configured mobile works with touch");
        check(required.canPlay(true, false), "Configured arcade works");
        check(!decoded.canPlay(false, false), "Partial mapping cannot replace touch");
        check(ControlMap.decode(required.encode()).isComplete(), "Saved setup remains complete");
        for (ControlMap.Binding binding : required.bindings) {
            ControlMap missing = ControlMap.decode(required.encode());
            missing.bindings.removeIf(b -> b.action == binding.action);
            check(!missing.isComplete(), "Every required action including Exit must be assigned");
        }
        check(!ControlMap.decode(required.encode()+"invalid").isComplete(), "Corruption cannot unlock launch");
        System.out.println("Game discovery and controller mapping regressions passed");
    }
}
