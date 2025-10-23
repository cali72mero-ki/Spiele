package com.example.funapp;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.MotionEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;

public class GameView extends SurfaceView implements Runnable {
    private Thread thread;
    private boolean running;
    private final Paint paint = new Paint();
    private float x = 100;
    private float y = 100;
    private float vx = 5;
    private float vy = 7;
    private final float radius = 50;

    public GameView(Context context) {
        super(context);
        paint.setColor(Color.RED);
    }

    @Override
    public void run() {
        SurfaceHolder holder = getHolder();
        while (running) {
            if (!holder.getSurface().isValid()) {
                continue;
            }
            Canvas canvas = holder.lockCanvas();
            if (canvas == null) {
                continue;
            }
            canvas.drawColor(Color.BLACK);
            x += vx;
            y += vy;
            int width = canvas.getWidth();
            int height = canvas.getHeight();
            if (x - radius < 0 || x + radius > width) {
                vx = -vx;
            }
            if (y - radius < 0 || y + radius > height) {
                vy = -vy;
            }
            canvas.drawCircle(x, y, radius, paint);
            holder.unlockCanvasAndPost(canvas);

            try {
                Thread.sleep(16);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public void resume() {
        running = true;
        thread = new Thread(this);
        thread.start();
    }

    public void pause() {
        running = false;
        if (thread != null) {
            try {
                thread.join();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (event.getAction() == MotionEvent.ACTION_DOWN) {
            vx = -vx;
            vy = -vy;
        }
        return true;
    }
}
