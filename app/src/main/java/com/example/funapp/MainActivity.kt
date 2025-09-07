package com.example.funapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawCircle
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                BouncingBall()
            }
        }
    }
}

@Composable
fun BouncingBall() {
    var position by remember { mutableStateOf(Offset(100f, 100f)) }
    var velocity by remember { mutableStateOf(Offset(5f, 7f)) }
    val radius = 50f
    var canvasSize by remember { mutableStateOf(Size.Zero) }

    LaunchedEffect(Unit) {
        while (true) {
            position += velocity
            val width = canvasSize.width
            val height = canvasSize.height
            if (position.x - radius < 0 || position.x + radius > width) {
                velocity = Offset(-velocity.x, velocity.y)
            }
            if (position.y - radius < 0 || position.y + radius > height) {
                velocity = Offset(velocity.x, -velocity.y)
            }
            delay(16L)
        }
    }

    Canvas(modifier = Modifier.fillMaxSize().background(Color.Black)) {
        canvasSize = size
        drawCircle(Color.Red, radius, position)
    }
}
